#!/usr/bin/env python3
"""
Sync VBWindows color status from latest RED:/YELLOW:/GREEN: comment.

Two tiers (see SKILL.md):
  Perfect — Color Status + Status Summary match the latest color comment
  Next    — health-* label + Status Summary (when Color Status is not on screen)

Default mode is draft (dry-run). Use --execute to apply. Runs as VME bot by default.

Requires JIRA_URL, JIRA_API_TOKEN, and JIRA_USERNAME or JIRA_EMAIL.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

BROWSE = "https://redhat.atlassian.net/browse"
LOG_FILE = Path("vbwindows_health_labels.log")

COLOR_STATUS_FIELD = "customfield_10712"
STATUS_SUMMARY_FIELD = "customfield_10814"
SCOPE_LABEL = "VBWindows"

STATUS_RE = re.compile(r"(?:^|\n)\s*(RED|YELLOW|GREEN)\s*:", re.IGNORECASE)
COLOR_TO_LABEL = {
    "RED": "health-red",
    "YELLOW": "health-yellow",
    "GREEN": "health-green",
}
COLOR_TO_STATUS_VALUE = {
    "RED": "Red",
    "YELLOW": "Yellow",
    "GREEN": "Green",
}
ALL_HEALTH_LABELS = set(COLOR_TO_LABEL.values())

ISSUE_FIELDS = [
    "summary",
    "status",
    "project",
    "labels",
    "comment",
    COLOR_STATUS_FIELD,
    STATUS_SUMMARY_FIELD,
]


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def jira_user() -> str:
    user = os.environ.get("JIRA_USERNAME") or os.environ.get("JIRA_EMAIL")
    if not user:
        print("Error: set JIRA_USERNAME or JIRA_EMAIL.", file=sys.stderr)
        sys.exit(1)
    return user


def jira_config() -> tuple[str, HTTPBasicAuth]:
    url = os.environ.get("JIRA_URL", "").rstrip("/")
    token = os.environ.get("JIRA_API_TOKEN", "")
    missing = [k for k, v in [("JIRA_URL", url), ("JIRA_API_TOKEN", token)] if not v]
    if missing:
        print(f"Error: missing {', '.join(missing)}.", file=sys.stderr)
        print("Copy env.bot.example to .env_vme_automation_bot and add credentials.", file=sys.stderr)
        sys.exit(1)
    return url, HTTPBasicAuth(jira_user(), token)


def jira_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def adf_to_text(body: object) -> str:
    parts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text":
                parts.append(str(node.get("text", "")))
            elif node.get("type") == "hardBreak":
                parts.append("\n")
            for child in node.get("content", []) or []:
                walk(child)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(body)
    return "".join(parts)


def parse_jira_dt(value: str) -> datetime:
    if value.endswith("+0000"):
        value = value[:-5] + "+00:00"
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_summary_text(text: str) -> str:
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"\s+", " ", text).strip()


def _extract_summary_date(text: str) -> str | None:
    match = re.search(r"(\d{4}-\d{2}-\d{2}):", text)
    return match.group(1) if match else None


def _extract_summary_body(text: str) -> str:
    lines = text.strip().split("\n", 1)
    if len(lines) > 1 and re.match(r"\d{4}-\d{2}-\d{2}:", lines[0].strip()):
        return normalize_summary_text(lines[1])
    return normalize_summary_text(text)


def latest_status_comment(comments: list[dict]) -> dict | None:
    latest: tuple[datetime, str, str, str] | None = None
    for comment in comments:
        text = adf_to_text(comment.get("body"))
        match = STATUS_RE.search(text)
        if not match:
            continue
        created = parse_jira_dt(comment["created"])
        color = match.group(1).upper()
        after_color = normalize_summary_text(text[match.end() :])
        author = comment.get("author", {}).get("displayName", "Unknown")
        if latest is None or created > latest[0]:
            latest = (created, color, author, after_color)
    if latest is None:
        return None
    created, color, author, after_color = latest
    return {
        "color": color,
        "date": created.strftime("%Y-%m-%d"),
        "author": author,
        "summary_text": after_color,
    }


def build_status_summary_adf(date_str: str, body_text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": f"{date_str}:"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": body_text},
                ],
            }
        ],
    }


def status_summary_plain(date_str: str, body_text: str) -> str:
    return f"{date_str}:\n{body_text}"


def health_labels_on_issue(labels: list[str]) -> list[str]:
    return [
        label
        for label in labels
        if label.lower() in ALL_HEALTH_LABELS or label.lower().startswith("health-")
    ]


def build_target_labels(labels: list[str], expected: str) -> list[str]:
    kept = [
        label
        for label in labels
        if label.lower() not in ALL_HEALTH_LABELS and not label.lower().startswith("health-")
    ]
    if not any(label.lower() == expected for label in labels):
        kept.append(expected)
    return kept


def get_editable_fields(
    session: requests.Session,
    base_url: str,
    auth: HTTPBasicAuth,
    issue_key: str,
    cache: dict[str, set[str]],
) -> set[str]:
    if issue_key not in cache:
        response = session.get(
            f"{base_url}/rest/api/3/issue/{issue_key}/editmeta",
            auth=auth,
            timeout=60,
        )
        if response.status_code == 200:
            cache[issue_key] = set(response.json().get("fields", {}).keys())
        else:
            cache[issue_key] = set()
    return cache[issue_key]


def search_issues(
    session: requests.Session,
    base_url: str,
    auth: HTTPBasicAuth,
    jql: str,
) -> list[dict]:
    url = f"{base_url}/rest/api/3/search/jql"
    all_issues: list[dict] = []
    start_at = 0
    while True:
        response = session.get(
            url,
            auth=auth,
            params={
                "jql": jql,
                "startAt": start_at,
                "maxResults": 100,
                "fields": ",".join(ISSUE_FIELDS),
            },
            timeout=120,
        )
        response.raise_for_status()
        batch = response.json().get("issues", [])
        all_issues.extend(batch)
        if len(batch) < 100:
            break
        start_at += 100
    return all_issues


def attribution_comment_body(tier: str, changes: list[str]) -> dict:
    summary = "; ".join(changes)
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Synced VBWindows {tier} status from latest color comment: {summary}."
                        ),
                    }
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "This issue was updated via Claude AI assistant.",
                        "marks": [{"type": "em"}],
                    }
                ],
            },
        ],
    }


def _current_color_status(fields: dict) -> str | None:
    value = fields.get(COLOR_STATUS_FIELD)
    if isinstance(value, dict):
        return value.get("value")
    return None


def _current_status_summary(fields: dict) -> str:
    value = fields.get(STATUS_SUMMARY_FIELD)
    if not value:
        return ""
    return adf_to_text(value).strip()


def _summary_matches(
    current: str,
    target_plain: str,
    latest_date: str,
    color_already_set: bool = False,
) -> bool:
    if not current.strip():
        return False

    current_norm = normalize_summary_text(current)
    target_norm = normalize_summary_text(target_plain)
    if current_norm == target_norm:
        return True

    current_date = _extract_summary_date(current)
    if current_date != latest_date:
        return False

    current_body = _extract_summary_body(current)
    target_body = _extract_summary_body(target_plain)
    if not current_body or not target_body:
        return color_already_set

    if current_body == target_body:
        return True

    # Jira may truncate Status Summary — treat same-date prefix overlap as a match.
    shorter, longer = (
        (current_body, target_body)
        if len(current_body) <= len(target_body)
        else (target_body, current_body)
    )
    if len(shorter) >= 40 and longer.startswith(shorter):
        return True

    # Color already reflects the latest comment — avoid rewriting minor text drift.
    if color_already_set:
        overlap = min(len(current_body), len(target_body), 80)
        if overlap >= 40 and current_body[:overlap] == target_body[:overlap]:
            return True

    return False


def _label_matches(labels: list[str], expected: str) -> bool:
    return any(label.lower() == expected for label in labels)


def evaluate_issue(
    labels: list[str],
    fields: dict,
    editable: set[str],
    latest: dict,
) -> dict:
    color = latest["color"]
    expected_label = COLOR_TO_LABEL[color]
    target_color_status = COLOR_TO_STATUS_VALUE[color]
    target_summary_adf = build_status_summary_adf(latest["date"], latest["summary_text"])
    target_summary_plain = status_summary_plain(latest["date"], latest["summary_text"])

    has_color_field = COLOR_STATUS_FIELD in editable
    has_summary_field = STATUS_SUMMARY_FIELD in editable
    has_labels_field = "labels" in editable
    tier = "perfect" if has_color_field else "next"

    current_color_status = _current_color_status(fields)
    current_status_summary = _current_status_summary(fields)
    current_health = health_labels_on_issue(labels)

    if not has_color_field and not has_summary_field and not has_labels_field:
        return {
            "tier": tier,
            "compliance": "skip_not_editable",
            "action": "skip_not_editable",
            "skip_reason": "VME bot cannot edit labels, Color Status, or Status Summary on this issue screen",
            "changes": [],
            "update_fields": {},
            "latest_color": color,
            "latest_color_date": latest["date"],
            "latest_color_author": latest["author"],
            "status_summary_text": latest["summary_text"],
            "expected_label": expected_label,
            "target_color_status": target_color_status,
            "target_status_summary": target_summary_plain,
            "current_health_labels": current_health,
            "current_color_status": current_color_status,
            "current_status_summary": current_status_summary,
            "has_color_status_field": has_color_field,
            "has_status_summary_field": has_summary_field,
            "has_labels_field": has_labels_field,
            "new_labels": labels,
        }

    changes: list[str] = []
    update_fields: dict = {}

    if tier == "perfect":
        color_ok = (current_color_status or "").lower() == target_color_status.lower()
        summary_ok = not has_summary_field or _summary_matches(
            current_status_summary,
            target_summary_plain,
            latest["date"],
            color_already_set=color_ok,
        )

        if has_color_field and not color_ok:
            changes.append(f"Color Status -> {target_color_status}")
            update_fields[COLOR_STATUS_FIELD] = {"value": target_color_status}

        if has_summary_field and not summary_ok:
            changes.append("Status Summary")
            update_fields[STATUS_SUMMARY_FIELD] = target_summary_adf

        compliance = "ok" if color_ok and summary_ok else "needs_update"
    else:
        label_ok = _label_matches(labels, expected_label) and not any(
            label.lower() != expected_label for label in current_health
        )
        summary_ok = not has_summary_field or _summary_matches(
            current_status_summary,
            target_summary_plain,
            latest["date"],
            color_already_set=label_ok,
        )

        if has_labels_field and not label_ok:
            changes.append(f"label -> {expected_label}")
            update_fields["labels"] = build_target_labels(labels, expected_label)

        if has_summary_field and not summary_ok:
            changes.append("Status Summary")
            update_fields[STATUS_SUMMARY_FIELD] = target_summary_adf

        compliance = "ok" if label_ok and summary_ok else "needs_update"

    return {
        "tier": tier,
        "compliance": compliance,
        "action": "update" if changes else compliance,
        "changes": changes,
        "update_fields": update_fields,
        "latest_color": color,
        "latest_color_date": latest["date"],
        "latest_color_author": latest["author"],
        "status_summary_text": latest["summary_text"],
        "expected_label": expected_label,
        "target_color_status": target_color_status,
        "target_status_summary": target_summary_plain,
        "current_health_labels": current_health,
        "current_color_status": current_color_status,
        "current_status_summary": current_status_summary,
        "has_color_status_field": has_color_field,
        "has_status_summary_field": has_summary_field,
        "has_labels_field": has_labels_field,
        "new_labels": update_fields.get("labels", labels),
    }


def build_plan(
    session: requests.Session,
    base_url: str,
    auth: HTTPBasicAuth,
    scope_label: str,
    issue_key: str | None,
) -> dict:
    if issue_key:
        jql = f"key = {issue_key}"
    else:
        jql = f'labels = "{scope_label}" ORDER BY key ASC'

    issues = search_issues(session, base_url, auth, jql)
    rows: list[dict] = []
    editmeta_cache: dict[str, set[str]] = {}

    for issue in issues:
        key = issue["key"]
        fields = issue["fields"]
        labels = list(fields.get("labels", []))
        comments = fields.get("comment", {}).get("comments", [])
        latest = latest_status_comment(comments)

        row: dict = {
            "key": key,
            "summary": fields.get("summary", ""),
            "status": fields.get("status", {}).get("name", ""),
            "project": fields.get("project", {}).get("key", ""),
            "labels": labels,
            "url": f"{BROWSE}/{key}",
        }

        if latest is None:
            row.update(
                {
                    "tier": None,
                    "compliance": "skip_no_color_comment",
                    "action": "skip_no_color_comment",
                    "latest_color": None,
                    "latest_color_date": None,
                    "latest_color_author": None,
                    "current_health_labels": health_labels_on_issue(labels),
                    "current_color_status": _current_color_status(fields),
                    "current_status_summary": _current_status_summary(fields),
                    "changes": [],
                    "update_fields": {},
                }
            )
            rows.append(row)
            continue

        editable = get_editable_fields(session, base_url, auth, key, editmeta_cache)
        evaluated = evaluate_issue(labels, fields, editable, latest)
        row.update(evaluated)
        rows.append(row)

    would_update = [row for row in rows if row["action"] == "update"]
    perfect_rows = [row for row in rows if row.get("tier") == "perfect"]
    next_rows = [row for row in rows if row.get("tier") == "next"]

    return {
        "scope_label": scope_label,
        "jql": jql,
        "total": len(rows),
        "perfect_total": len(perfect_rows),
        "perfect_ok": sum(1 for row in perfect_rows if row["compliance"] == "ok"),
        "next_total": len(next_rows),
        "next_ok": sum(1 for row in next_rows if row["compliance"] == "ok"),
        "would_update": would_update,
        "skip_no_color_comment": sum(1 for row in rows if row["action"] == "skip_no_color_comment"),
        "skip_not_editable": sum(1 for row in rows if row["action"] == "skip_not_editable"),
        "rows": rows,
    }


def execute_updates(
    session: requests.Session,
    base_url: str,
    auth: HTTPBasicAuth,
    updates: list[dict],
) -> tuple[list[str], list[str]]:
    log_lines: list[str] = []
    errors: list[str] = []
    for row in updates:
        key = row["key"]
        try:
            response = session.put(
                f"{base_url}/rest/api/3/issue/{key}",
                auth=auth,
                json={"fields": row["update_fields"]},
                timeout=60,
            )
            response.raise_for_status()
            comment = session.post(
                f"{base_url}/rest/api/3/issue/{key}/comment",
                auth=auth,
                json={"body": attribution_comment_body(row["tier"], row["changes"])},
                timeout=60,
            )
            comment.raise_for_status()
            line = f"{key} ({row['tier']}): {', '.join(row['changes'])}"
            print(line)
            log_lines.append(line)
        except requests.HTTPError as exc:
            detail = ""
            if exc.response is not None:
                detail = exc.response.text[:300]
            msg = f"{key}: skipped ({exc}); {detail}"
            print(msg, file=sys.stderr)
            errors.append(msg)
    return log_lines, errors


def render_markdown(plan: dict, draft: bool) -> str:
    mode = "DRAFT" if draft else "EXECUTED"
    lines = [
        f"# VBWindows health status sync ({mode})",
        "",
        f"- Scope label: `{plan['scope_label']}`",
        f"- JQL: `{plan['jql']}`",
        f"- Total issues: {plan['total']}",
        f"- **Perfect tier** (Color Status + Status Summary): {plan['perfect_ok']}/{plan['perfect_total']} ok",
        f"- **Next tier** (health label + Status Summary): {plan['next_ok']}/{plan['next_total']} ok",
        f"- Would update: {len(plan['would_update'])}",
        f"- No color comment: {plan['skip_no_color_comment']}",
        f"- Not editable by bot: {plan.get('skip_not_editable', 0)}",
        "",
        "**Perfect** = `VBWindows` + Color Status + Status Summary match latest color comment.",
        "**Next** = `VBWindows` + `health-*` label + Status Summary (when Color Status is not on screen).",
        "",
    ]

    if plan["would_update"]:
        lines.extend(
            [
                "## Changes",
                "",
                "| Key | Tier | Color | Date | Changes | Status Summary preview |",
                "|-----|------|-------|------|---------|------------------------|",
            ]
        )
        for row in plan["would_update"]:
            preview = row.get("target_status_summary", "")
            preview = preview.replace("|", "\\|").replace("\n", " ")
            if len(preview) > 80:
                preview = preview[:77] + "..."
            changes = "; ".join(row["changes"])
            lines.append(
                f"| [{row['key']}]({row['url']}) | {row['tier']} | {row['latest_color']} | "
                f"{row['latest_color_date']} | {changes} | {preview} |"
            )
        lines.append("")

    for tier_name, tier_key in [("Perfect tier", "perfect"), ("Next tier", "next")]:
        items = [row for row in plan["rows"] if row.get("tier") == tier_key]
        if not items:
            continue
        lines.extend([f"## {tier_name}", ""])
        if tier_key == "perfect":
            lines.append("| Key | Color | Color Status | Status Summary | Compliance |")
            lines.append("|-----|-------|--------------|----------------|------------|")
            for row in items:
                summary_state = "set" if row.get("current_status_summary") else "missing"
                compliance = row["compliance"]
                if row["action"] == "update":
                    compliance = "needs update"
                lines.append(
                    f"| [{row['key']}]({row['url']}) | {row['latest_color']} | "
                    f"{row.get('current_color_status') or '—'} | {summary_state} | {compliance} |"
                )
        else:
            lines.append("| Key | Color | Health label | Status Summary | Compliance |")
            lines.append("|-----|-------|--------------|----------------|------------|")
            for row in items:
                health = ", ".join(row.get("current_health_labels", [])) or "—"
                summary_state = "set" if row.get("current_status_summary") else "missing"
                compliance = row["compliance"]
                if row["action"] == "update":
                    compliance = "needs update"
                lines.append(
                    f"| [{row['key']}]({row['url']}) | {row['latest_color']} | "
                    f"{health} | {summary_state} | {compliance} |"
                )
        lines.append("")

    no_color = [row for row in plan["rows"] if row["action"] == "skip_no_color_comment"]
    if no_color:
        lines.extend([f"## No color comment ({len(no_color)})", ""])
        for row in no_color:
            lines.append(f"- [{row['key']}]({row['url']}) — {row['summary']}")
        lines.append("")

    not_editable = [row for row in plan["rows"] if row["action"] == "skip_not_editable"]
    if not_editable:
        lines.extend([f"## Not editable by bot ({len(not_editable)})", ""])
        for row in not_editable:
            reason = row.get("skip_reason", "fields not on edit screen")
            lines.append(f"- [{row['key']}]({row['url']}) — {reason}")
        lines.append("")

    if draft and plan["would_update"]:
        lines.extend(
            [
                "Run with `--execute` to apply (uses VME Automation Bot by default).",
                "",
            ]
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sync VBWindows color status from latest RED:/YELLOW:/GREEN: comment. "
            "Perfect tier: Color Status + Status Summary. "
            "Next tier: health label + Status Summary."
        )
    )
    parser.add_argument(
        "--scope-label",
        default=SCOPE_LABEL,
        help=f'Issue scope label (default: {SCOPE_LABEL})',
    )
    parser.add_argument(
        "--issue",
        metavar="KEY",
        help="Process a single issue key instead of all scoped issues",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Override env file (default: .env_vme_automation_bot, or .env_jira with --personal)",
    )
    parser.add_argument(
        "--personal",
        action="store_true",
        help="Use personal .env_jira instead of VME automation bot (not recommended)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply updates and comments (default: draft only)",
    )
    parser.add_argument("--json", action="store_true", help="Output plan as JSON")
    args = parser.parse_args()

    if args.env_file:
        env_path = args.env_file
    elif args.personal:
        env_path = Path(".env_jira")
    else:
        env_path = Path(".env_vme_automation_bot")

    using_bot = env_path.name == ".env_vme_automation_bot"
    load_env_file(env_path)
    base_url, auth = jira_config()
    session = jira_session()

    plan = build_plan(session, base_url, auth, args.scope_label, args.issue)

    if args.json:
        print(json.dumps(plan, indent=2))
        return

    draft = not args.execute
    print(render_markdown(plan, draft=draft))

    if not args.execute:
        return

    updates = plan["would_update"]
    if not updates:
        print("Nothing to update.")
        return

    if not using_bot:
        print(
            "\nWARNING: Personal account will be auto-added as a watcher on each "
            "updated issue. Prefer the default VME automation bot (omit --personal).",
            file=sys.stderr,
        )
    else:
        print(f"\nUsing VME Automation Bot ({jira_user()})")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\nEXECUTING — updating {len(updates)} issue(s)...")
    log_lines = [
        f"Run started {stamp} execute=True bot={using_bot} user={jira_user()}",
        f"Scope label: {args.scope_label}",
        f"Would update: {len(updates)}",
    ]
    applied, errors = execute_updates(session, base_url, auth, updates)
    log_lines.extend(applied)
    log_lines.extend(errors)
    LOG_FILE.write_text(
        (LOG_FILE.read_text() + "\n".join(log_lines) + "\n")
        if LOG_FILE.exists()
        else "\n".join(log_lines) + "\n"
    )
    if errors and not applied:
        print("\nAll updates failed.", file=sys.stderr)
        sys.exit(1)
    if errors:
        print(f"\nCompleted with {len(errors)} skipped issue(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
