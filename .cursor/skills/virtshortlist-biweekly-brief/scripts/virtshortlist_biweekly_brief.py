#!/usr/bin/env python3
"""
VirtShortList biweekly executive brief — draft then execute.

Draft (read-only): fetch VirtShortList items and source status text; write briefs JSON
for agent review. Execute (VME bot): overwrite Status Summary + Red Hat Employee comment.

Usage:
  python virtshortlist_biweekly_brief.py draft
  python virtshortlist_biweekly_brief.py draft --out briefs.json
  python virtshortlist_biweekly_brief.py execute --briefs briefs.json
  python virtshortlist_biweekly_brief.py execute --briefs briefs.json --replace-comments
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

BROWSE = "https://redhat.atlassian.net/browse"
LOG_FILE = Path("virtshortlist_biweekly_brief.log")

JQL = "labels = virtshortlist AND issuetype in (Feature, Outcome) ORDER BY key ASC"
ARCHITECT_FIELD = "customfield_10467"
COLOR_STATUS_FIELD = "customfield_10712"
STATUS_SUMMARY_FIELD = "customfield_10814"

COMMENT_MARKER = "Biweekly Report status:"
AI_ATTRIBUTION = "Status Summary updated via Claude AI assistant."
SEE_COMMENT_HINTS = ("see latest status comment", "see latest comment")

FETCH_FIELDS = (
    f"summary,status,issuetype,updated,assignee,{ARCHITECT_FIELD},"
    f"{COLOR_STATUS_FIELD},{STATUS_SUMMARY_FIELD},comment"
)

COLOR_ORDER = {"Red": 0, "Yellow": 1, "Green": 2, "Unset": 3, "—": 3, "": 4}


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
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


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
        sys.exit(1)
    return url, HTTPBasicAuth(jira_user(), token)


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


def text_to_adf(text: str) -> dict:
    paragraphs = []
    for block in text.split("\n\n"):
        lines = block.split("\n")
        content: list[dict] = []
        for line in lines:
            if content:
                content.append({"type": "hardBreak"})
            content.append({"type": "text", "text": line})
        paragraphs.append({"type": "paragraph", "content": content})
    return {"type": "doc", "version": 1, "content": paragraphs}


def field_text(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        if "value" in raw:
            return str(raw["value"]).strip()
        if "content" in raw:
            return adf_to_text(raw).strip()
    return str(raw).strip()


def color_display(raw: object) -> str:
    value = field_text(raw)
    return value if value else "Unset"


def strip_leading_date(text: str) -> str:
    text = text.strip()
    match = re.match(r"^\d{4}-\d{2}-\d{2}:\s*", text)
    if match:
        return text[match.end() :].strip()
    return text


def needs_comment_fallback(text: str) -> bool:
    if not text:
        return True
    lower = text.lower()
    return any(h in lower for h in SEE_COMMENT_HINTS)


def log_line(message: str) -> None:
    print(message)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def search_issues(base_url: str, auth: HTTPBasicAuth) -> list[dict]:
    r = requests.get(
        f"{base_url}/rest/api/3/search/jql",
        auth=auth,
        params={"jql": JQL, "maxResults": 100, "fields": FETCH_FIELDS},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("issues", [])


def fetch_comments(base_url: str, auth: HTTPBasicAuth, key: str, limit: int = 10) -> list[dict]:
    r = requests.get(
        f"{base_url}/rest/api/3/issue/{key}/comment",
        auth=auth,
        params={"maxResults": limit, "orderBy": "-created"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("comments", [])


def resolve_source_text(
    base_url: str,
    auth: HTTPBasicAuth,
    key: str,
    status_summary: str,
) -> tuple[str, str]:
    """Return (source_text, source_kind)."""
    if status_summary and not needs_comment_fallback(status_summary):
        return status_summary, "status_summary"

    for comment in fetch_comments(base_url, auth, key):
        body = adf_to_text(comment.get("body")).strip()
        if body and not body.startswith("Status Summary refreshed"):
            if COMMENT_MARKER not in body and AI_ATTRIBUTION not in body:
                created = (comment.get("created") or "")[:10]
                return f"{created}: {body}" if created else body, "latest_comment"

    if status_summary:
        return status_summary, "status_summary"

    return "", "empty"


def parse_row(base_url: str, auth: HTTPBasicAuth, issue: dict, report_date: str) -> dict:
    fields = issue["fields"]
    key = issue["key"]
    status_summary = field_text(fields.get(STATUS_SUMMARY_FIELD))
    source_text, source_kind = resolve_source_text(base_url, auth, key, status_summary)
    architect = fields.get(ARCHITECT_FIELD)
    architect_name = architect.get("displayName", "—") if architect else "—"

    return {
        "key": key,
        "url": f"{BROWSE}/{key}",
        "title": fields.get("summary", ""),
        "type": fields.get("issuetype", {}).get("name", ""),
        "workflow_status": fields.get("status", {}).get("name", ""),
        "color_status": color_display(fields.get(COLOR_STATUS_FIELD)),
        "updated": (fields.get("updated") or "")[:10],
        "architect": architect_name,
        "source_status_summary": status_summary,
        "source_text": source_text,
        "source_kind": source_kind,
        "report_date": report_date,
        "exec_brief": "",
    }


def fetch_draft(base_url: str, auth: HTTPBasicAuth, report_date: str) -> dict:
    rows = [parse_row(base_url, auth, issue, report_date) for issue in search_issues(base_url, auth)]
    rows.sort(key=lambda r: (COLOR_ORDER.get(r["color_status"], 9), r["key"]))
    return {
        "report_date": report_date,
        "generated": date.today().isoformat(),
        "jql": JQL,
        "items": rows,
    }


def status_summary_value(report_date: str, exec_brief: str) -> str:
    brief = exec_brief.strip()
    if brief.startswith(f"{report_date}:"):
        return brief
    return f"{report_date}: {brief}"


def comment_body(item: dict) -> str:
    report_date = item["report_date"]
    color = item["color_status"]
    workflow = item["workflow_status"]
    brief = item["exec_brief"].strip()
    return (
        f"{report_date}: {color}: Biweekly Report status: {workflow}\n\n"
        f"Executive summary: {brief}\n\n"
        f"---\n"
        f"{AI_ATTRIBUTION}"
    )


def markdown_draft(data: dict) -> str:
    lines = [
        "# VirtShortList Biweekly Executive Brief — DRAFT",
        "",
        f"- **Report date:** {data['report_date']}",
        f"- **Items:** {len(data['items'])}",
        "",
        "_Review exec briefs below. Fill `exec_brief` in the JSON file, then run `execute`._",
        "",
        "| Key | Color | Status | Source (Jira) | Executive brief (draft) |",
        "|-----|-------|--------|---------------|-------------------------|",
    ]
    for item in data["items"]:
        key = f"[{item['key']}]({item['url']})"
        source = item.get("source_text") or item.get("source_status_summary") or "—"
        source = source.replace("|", "\\|").replace("\n", " ")
        if len(source) > 120:
            source = source[:119] + "…"
        brief = item.get("exec_brief") or "_(agent: draft required)_"
        brief = brief.replace("|", "\\|")
        lines.append(
            f"| {key} | {item['color_status']} | {item['workflow_status']} | {source} | {brief} |"
        )
    lines.append("")
    return "\n".join(lines)


def load_briefs(path: Path) -> dict:
    if not path.is_file():
        print(f"Error: briefs file not found: {path}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", [])
    missing = [i["key"] for i in items if not str(i.get("exec_brief", "")).strip()]
    if missing:
        print("Error: exec_brief missing for: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)
    return data


def get_myself(base_url: str, auth: HTTPBasicAuth) -> dict:
    r = requests.get(f"{base_url}/rest/api/3/myself", auth=auth, timeout=60)
    r.raise_for_status()
    return r.json()


def remove_bot_biweekly_comments(
    base_url: str,
    auth: HTTPBasicAuth,
    bot_account_id: str,
    key: str,
) -> int:
    r = requests.get(
        f"{base_url}/rest/api/3/issue/{key}/comment",
        auth=auth,
        params={"maxResults": 50, "orderBy": "-created"},
        timeout=60,
    )
    r.raise_for_status()
    removed = 0
    for comment in r.json().get("comments", []):
        author = comment.get("author", {})
        if author.get("accountId") != bot_account_id:
            continue
        body = adf_to_text(comment.get("body"))
        if COMMENT_MARKER not in body:
            continue
        dr = requests.delete(
            f"{base_url}/rest/api/3/issue/{key}/comment/{comment['id']}",
            auth=auth,
            timeout=60,
        )
        if dr.status_code in (200, 204):
            removed += 1
    return removed


def remove_watcher(base_url: str, auth: HTTPBasicAuth, key: str, account_id: str) -> str:
    r = requests.delete(
        f"{base_url}/rest/api/3/issue/{key}/watchers",
        auth=auth,
        params={"accountId": account_id},
        timeout=60,
    )
    if r.status_code in (200, 204):
        return "OK"
    if r.status_code == 404:
        return "OK (not watching)"
    return f"FAIL {r.status_code}"


def execute_updates(
    base_url: str,
    auth: HTTPBasicAuth,
    data: dict,
    *,
    replace_comments: bool,
) -> dict:
    myself = get_myself(base_url, auth)
    account_id = myself["accountId"]
    actor = myself.get("emailAddress") or jira_user()

    log_line("")
    log_line("=" * 72)
    log_line(f"VirtShortList biweekly execute — {data['report_date']} — {actor}")

    results = []
    for item in data["items"]:
        key = item["key"]
        row = {"key": key, "field": "pending", "comment": "pending", "unwatch": "pending"}
        summary_text = status_summary_value(item["report_date"], item["exec_brief"])

        try:
            r = requests.put(
                f"{base_url}/rest/api/3/issue/{key}",
                auth=auth,
                headers={"Content-Type": "application/json"},
                json={"fields": {STATUS_SUMMARY_FIELD: text_to_adf(summary_text)}},
                timeout=60,
            )
            if r.status_code >= 400:
                row["field"] = f"FAIL {r.status_code}: {r.text[:200]}"
                results.append(row)
                log_line(f"{key}: FIELD FAIL")
                continue
            row["field"] = "OK"

            if replace_comments:
                removed = remove_bot_biweekly_comments(base_url, auth, account_id, key)
                row["comments_removed"] = removed

            r = requests.post(
                f"{base_url}/rest/api/3/issue/{key}/comment",
                auth=auth,
                headers={"Content-Type": "application/json"},
                json={
                    "body": text_to_adf(comment_body(item)),
                    "visibility": {"type": "group", "value": "Red Hat Employee"},
                },
                timeout=60,
            )
            if r.status_code >= 400:
                row["comment"] = f"FAIL {r.status_code}: {r.text[:200]}"
                results.append(row)
                log_line(f"{key}: COMMENT FAIL")
                continue
            row["comment"] = "OK"
            row["unwatch"] = remove_watcher(base_url, auth, key, account_id)
            log_line(f"{key}: OK | comment OK | unwatch {row['unwatch']}")
        except requests.RequestException as exc:
            row["field"] = f"ERROR: {exc}"
            log_line(f"{key}: ERROR {exc}")
        results.append(row)

    ok = sum(1 for r in results if r.get("field") == "OK" and r.get("comment") == "OK")
    log_line(f"Complete: {ok}/{len(data['items'])}")
    log_line("=" * 72)
    return {"actor": actor, "ok": ok, "total": len(data["items"]), "results": results}


def cmd_draft(args: argparse.Namespace) -> None:
    load_env_file(args.env_file)
    base_url, auth = jira_config()
    data = fetch_draft(base_url, auth, args.date)

    if args.out:
        args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote draft JSON: {args.out}")

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(markdown_draft(data))


def cmd_execute(args: argparse.Namespace) -> None:
    load_env_file(args.env_file)
    base_url, auth = jira_config()
    data = load_briefs(args.briefs)

    if args.dry_run:
        print("# Execute preview (dry-run)\n")
        for item in data["items"]:
            print(f"## {item['key']}")
            print(f"Status Summary: {status_summary_value(item['report_date'], item['exec_brief'])}")
            print()
            print(comment_body(item))
            print()
        return

    summary = execute_updates(base_url, auth, data, replace_comments=args.replace_comments)
    print(f"\nActing as: {summary['actor']}")
    print(f"Complete: {summary['ok']}/{summary['total']}")
    for row in summary["results"]:
        if row.get("field") != "OK" or row.get("comment") != "OK":
            print(json.dumps(row))
    if summary["ok"] != summary["total"]:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="VirtShortList biweekly executive brief")
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Env file (default: .env_jira for draft, .env_vme_automation_bot for execute)",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Report date prefix (default: today YYYY-MM-DD)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    draft = sub.add_parser("draft", help="Fetch items and output draft (no Jira writes)")
    draft.add_argument("--out", type=Path, help="Write draft JSON for agent to fill exec_brief")
    draft.add_argument("--json", action="store_true", help="Print JSON to stdout")
    draft.set_defaults(func=cmd_draft)

    execute = sub.add_parser("execute", help="Post approved briefs as VME bot")
    execute.add_argument("--briefs", type=Path, required=True, help="Approved briefs JSON")
    execute.add_argument(
        "--replace-comments",
        action="store_true",
        help="Remove prior bot Biweekly Report comments before posting",
    )
    execute.add_argument("--dry-run", action="store_true", help="Preview writes without posting")
    execute.set_defaults(func=cmd_execute)

    args = parser.parse_args()

    if args.env_file is None:
        if args.command == "execute":
            args.env_file = Path(".env_vme_automation_bot")
        else:
            for candidate in (Path(".env_jira"), Path(".env_wilker_jira")):
                if candidate.is_file():
                    args.env_file = candidate
                    break
            else:
                args.env_file = Path(".env_jira")

    args.func(args)


if __name__ == "__main__":
    main()
