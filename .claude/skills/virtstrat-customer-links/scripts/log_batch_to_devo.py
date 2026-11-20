#!/usr/bin/env python3
"""
Post a Customer Intelligence create-batch log comment on the DEVO hygiene story.

Default issue: DEVO-288 (Q4 2026 Customer Links hygiene). Override with
--devo-issue or CUSTOMER_LINKS_DEVO_ISSUE.

Reads virtstrat_customer_links_draft.json (mode=executed) and posts a summary
plus Feature <- FR (mdm_pk) lines. No customer names. Keeps watcher on DEVO.
Adds ai-sdlc-assisted if missing. Uses personal Jira creds by default
(.env_wilker_jira / .env_jira) so the log is under the operator; optionally
--bot for VME Automation Bot (still Red Hat Employee visibility).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from jira import JIRA

SCRIPT_DIR = Path(__file__).resolve().parent


def find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / ".git").is_dir() or (p / "run_copy_customer_links_to_virtstrat.sh").is_file():
            return p
    return start.parents[3]


REPO_ROOT = find_repo_root(SCRIPT_DIR)
DEFAULT_DRAFT = REPO_ROOT / "virtstrat_customer_links_draft.json"
DEFAULT_DEVO = os.environ.get("CUSTOMER_LINKS_DEVO_ISSUE", "DEVO-288")
AI_LABEL = "ai-sdlc-assisted"


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip("'").strip('"')
    return env


def connect(env_name: str, default_user: str | None = None) -> JIRA:
    env = load_env_file(REPO_ROOT / env_name)
    url = env.get("JIRA_URL") or os.environ.get("JIRA_URL") or "https://redhat.atlassian.net"
    user = env.get("JIRA_USERNAME") or env.get("JIRA_EMAIL") or default_user
    token = env.get("JIRA_API_TOKEN")
    if not user or not token:
        print(f"Missing credentials in {env_name}", file=sys.stderr)
        sys.exit(1)
    return JIRA(server=url, basic_auth=(user, token))


def pick_batch_rows(draft: dict) -> list[dict]:
    """Prefer rows created in the latest executed batch."""
    created = list(draft.get("created") or [])
    touched = set(draft.get("touched_features") or [])
    executed_at = str(draft.get("executed_at") or "")
    day = executed_at[:10] if executed_at else ""

    if day:
        batch = [
            c
            for c in created
            if str(c.get("created_at") or "").startswith(day) and not c.get("already_existed")
        ]
        if batch:
            return batch
    if touched:
        batch = [
            c
            for c in created
            if c.get("virtstrat_key") in touched and not c.get("already_existed")
        ]
        if batch:
            return batch
    return [c for c in created if not c.get("already_existed")]


def build_comment(draft: dict, rows: list[dict]) -> str:
    by: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by[str(row.get("virtstrat_key") or "")].append(row)

    executed = str(draft.get("executed_at") or "")[:10] or date.today().isoformat()
    cnv = sum(1 for r in rows if str(r.get("source_key") or "").startswith("CNV-"))
    mtv = sum(1 for r in rows if str(r.get("source_key") or "").startswith("MTV-"))
    alts = draft.get("failures_resolved_as_alternate_mdm") or []

    lines = [
        f"Customer Intelligence link hygiene batch ({executed})",
        "",
        "Action: Copied missing Customer Links from linked CNV/MTV Feature Requests "
        "onto VIRTSTRAT Features via rh_customers CLI (Production). Live-verified before create.",
        "",
        "Summary:",
        f"- Customer links created: {len(rows)}",
        f"- VIRTSTRAT Features updated: {len(by)}",
        f"- Sources: {cnv} CNV FR, {mtv} MTV FR",
        "- Context: affected_by (unless noted in log)",
        "- Scope: Feature Request sources only (issuetype 10111)",
        "- Attribution: Red Hat Employee comments on Features via VME Automation Bot "
        '("Customer links were updated." + AI assistance note); ai-sdlc-assisted ensured',
        "",
        "Log (VIRTSTRAT Feature <- source FR, customer MDM pk):",
    ]

    def sort_key(k: str) -> tuple[str, int]:
        parts = k.split("-", 1)
        try:
            return (parts[0], int(parts[1]))
        except Exception:
            return (k, 0)

    for vs in sorted(by, key=sort_key):
        for row in sorted(by[vs], key=lambda r: str(r.get("customer_mdm_pk") or "")):
            src = row.get("source_key") or "?"
            mdm = row.get("customer_mdm_pk")
            ctx = row.get("context") or "affected_by"
            suffix = f" context={ctx}" if ctx != "affected_by" else ""
            lines.append(f"- {vs} <- {src} (mdm_pk={mdm}){suffix}")

    if alts:
        lines.append("")
        lines.append(
            "Warehouse alternate mdm_id rows (already covered by canonical pk creates):"
        )
        for a in alts:
            lines.append(
                f"- {a.get('virtstrat_key')}: warehouse {a.get('warehouse_mdm')} "
                f"→ canonical {a.get('canonical_mdm_pk')}"
            )

    lines.extend(
        [
            "",
            "---",
            "*Comment added with OpenAI assistance.*",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--devo-issue", default=DEFAULT_DEVO)
    parser.add_argument("--bot", action="store_true", help="Post as VME Automation Bot")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print comment body only; do not post",
    )
    args = parser.parse_args()

    if not args.draft.is_file():
        print(f"Missing draft: {args.draft}", file=sys.stderr)
        sys.exit(1)

    draft = json.loads(args.draft.read_text())
    rows = pick_batch_rows(draft)
    if not rows:
        print("No created rows to log in draft", file=sys.stderr)
        sys.exit(2)

    body = build_comment(draft, rows)
    if args.dry_run:
        print(body)
        return

    if args.bot:
        jira = connect(".env_vme_automation_bot", "vme-automation-bot@redhat.com")
    else:
        personal = None
        for name in (".env_wilker_jira", ".env_jira"):
            if (REPO_ROOT / name).is_file():
                personal = connect(name)
                break
        if personal is None:
            print("No personal .env_wilker_jira / .env_jira found", file=sys.stderr)
            sys.exit(1)
        jira = personal

    key = args.devo_issue.strip().upper()
    issue = jira.issue(key, fields="labels,project")
    labels = list(getattr(issue.fields, "labels", None) or [])
    if AI_LABEL not in labels:
        labels.append(AI_LABEL)
        issue.update(fields={"labels": labels})
        print(f"Added label {AI_LABEL} on {key}")

    jira.add_comment(
        key,
        body,
        visibility={"type": "group", "value": "Red Hat Employee"},
    )
    print(f"Batch log posted on {key} ({len(rows)} link(s), Red Hat Employee)")
    print("  Watcher kept (DEVO)")


if __name__ == "__main__":
    main()
