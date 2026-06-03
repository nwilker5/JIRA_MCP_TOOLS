#!/usr/bin/env python3
"""
VirtShortList report: Features and Outcomes with label virtshortlist,
split by whether they were updated this calendar week (Jira startOfWeek).

Requires JIRA_URL, JIRA_API_TOKEN, and JIRA_USERNAME or JIRA_EMAIL.
Optional: source .env_jira or pass --env-file path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import requests
from requests.auth import HTTPBasicAuth

ARCHITECT_FIELD = "customfield_10467"
DEFAULT_JQL_BASE = "labels = virtshortlist AND issuetype in (Feature, Outcome)"
NO_CONTACT = "—"


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
        print(
            "Error: set JIRA_USERNAME or JIRA_EMAIL in your environment.",
            file=sys.stderr,
        )
        sys.exit(1)
    return user


def jira_config() -> tuple[str, HTTPBasicAuth]:
    url = os.environ.get("JIRA_URL", "").rstrip("/")
    token = os.environ.get("JIRA_API_TOKEN", "")
    missing = []
    if not url:
        missing.append("JIRA_URL")
    if not token:
        missing.append("JIRA_API_TOKEN")
    if missing:
        print(f"Error: missing {', '.join(missing)}.", file=sys.stderr)
        print("Copy env.jira.example to .env_jira and add your credentials.", file=sys.stderr)
        sys.exit(1)
    return url, HTTPBasicAuth(jira_user(), token)


def search(base_url: str, auth: HTTPBasicAuth, jql: str) -> list[dict]:
    fields = f"summary,status,issuetype,updated,assignee,{ARCHITECT_FIELD}"
    r = requests.get(
        f"{base_url}/rest/api/3/search/jql",
        auth=auth,
        params={"jql": jql, "maxResults": 100, "fields": fields},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("issues", [])


def user_contact(user: dict | None) -> dict:
    if not user:
        return {"name": NO_CONTACT, "email": None}
    return {
        "name": user.get("displayName") or NO_CONTACT,
        "email": user.get("emailAddress"),
    }


def parse_row(issue: dict, base_url: str) -> dict:
    f = issue["fields"]
    architect = user_contact(f.get(ARCHITECT_FIELD))
    assignee = user_contact(f.get("assignee"))
    contact = contact_for_issue(architect, assignee)
    return {
        "key": issue["key"],
        "summary": f.get("summary", ""),
        "type": f.get("issuetype", {}).get("name", ""),
        "status": f.get("status", {}).get("name", ""),
        "updated": (f.get("updated") or "")[:10],
        "assignee": assignee["name"],
        "assignee_email": assignee["email"],
        "architect": architect["name"],
        "architect_email": architect["email"],
        "contact_name": contact["name"],
        "contact_email": contact["email"],
        "contact_role": contact["role"],
        "url": f"{base_url}/browse/{issue['key']}",
    }


def contact_for_issue(architect: dict, assignee: dict) -> dict:
    """Recipient: architect if set, otherwise assignee."""
    if architect["name"] != NO_CONTACT:
        return {**architect, "role": "architect"}
    if assignee["name"] != NO_CONTACT:
        return {**assignee, "role": "assignee"}
    return {"name": NO_CONTACT, "email": None, "role": "none"}


def fetch_report(base_url: str, auth: HTTPBasicAuth) -> dict:
    stale_jql = f"{DEFAULT_JQL_BASE} AND updated < startOfWeek() ORDER BY updated ASC"
    fresh_jql = f"{DEFAULT_JQL_BASE} AND updated >= startOfWeek() ORDER BY updated DESC"
    stale = [parse_row(i, base_url) for i in search(base_url, auth, stale_jql)]
    fresh = [parse_row(i, base_url) for i in search(base_url, auth, fresh_jql)]
    all_rows = stale + fresh
    missing_architect = [r["key"] for r in all_rows if r["architect"] == NO_CONTACT]
    no_contact = [r["key"] for r in stale if r["contact_role"] == "none"]
    email_drafts = build_email_drafts(stale)
    return {
        "total": len(all_rows),
        "stale_count": len(stale),
        "fresh_count": len(fresh),
        "missing_architect": missing_architect,
        "no_contact": no_contact,
        "stale": stale,
        "fresh": fresh,
        "email_drafts": email_drafts,
    }


def build_email_drafts(stale: list[dict]) -> list[dict]:
    """One draft per contact (architect, or assignee when architect unset)."""
    by_recipient: dict[str, dict] = defaultdict(
        lambda: {"name": "", "email": None, "role": "", "issues": []}
    )

    for row in stale:
        if row["contact_role"] == "none":
            continue
        key = row["contact_email"] or row["contact_name"]
        bucket = by_recipient[key]
        bucket["name"] = row["contact_name"]
        bucket["email"] = row["contact_email"]
        bucket["role"] = row["contact_role"]
        bucket["issues"].append(row)

    drafts = []
    for bucket in sorted(by_recipient.values(), key=lambda b: b["name"].lower()):
        drafts.append(format_draft(bucket))
    return drafts


def format_draft(bucket: dict) -> dict:
    name = bucket["name"]
    email = bucket["email"]
    role = bucket["role"]
    issues = bucket["issues"]
    role_label = "Architect" if role == "architect" else "Assignee"

    issue_lines = []
    for r in sorted(issues, key=lambda x: x["updated"]):
        issue_lines.append(
            f"  • {r['key']} ({r['type']}, {r['status']}) — last updated {r['updated']}\n"
            f"    {r['summary']}\n"
            f"    {r['url']}"
        )
    issue_block = "\n\n".join(issue_lines)

    subject = (
        f"VirtShortList update request — {len(issues)} item"
        f"{'' if len(issues) == 1 else 's'} not updated this week"
    )

    greeting = f"Hi {name.split()[0]}," if name != NO_CONTACT else "Hi,"

    body = f"""{greeting}

I'm following up on VirtShortList ({role_label} on the item{'s' if len(issues) != 1 else ''} below) that {'have' if len(issues) != 1 else 'has'} not been updated in Jira this calendar week. When you have a moment, could you please refresh the ticket(s) with a brief status (or note if no change is needed)?

{issue_block}

Thank you,
"""

    mailto = ""
    if email:
        params = f"subject={quote(subject)}&body={quote(body.strip())}"
        mailto = f"mailto:{email}?{params}"

    return {
        "to_name": name,
        "to_email": email,
        "contact_role": role,
        "subject": subject,
        "body": body.strip(),
        "mailto": mailto,
        "issue_keys": [r["key"] for r in issues],
    }


def truncate(text: str, n: int = 55) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def markdown_report(data: dict, *, include_email_offer: bool = True) -> str:
    lines = [
        "# VirtShortList report",
        "",
        f"- **Total:** {data['total']}",
        f"- **Updated this week:** {data['fresh_count']}",
        f"- **Not updated this week:** {data['stale_count']}",
        f"- **Missing Architect:** {len(data['missing_architect'])}",
        "",
        "_Week boundary uses Jira `startOfWeek()` on the calendar week._",
        "",
    ]

    def table(title: str, rows: list[dict]) -> None:
        lines.append(f"## {title} ({len(rows)})")
        lines.append("")
        if not rows:
            lines.append("_None._")
            lines.append("")
            return
        lines.append(
            "| Key | Type | Status | Last updated | Architect | Assignee | Summary |"
        )
        lines.append("|-----|------|--------|--------------|-----------|----------|---------|")
        for r in rows:
            key = f"[{r['key']}]({r['url']})"
            lines.append(
                f"| {key} | {r['type']} | {r['status']} | {r['updated']} | "
                f"{r['architect']} | {r['assignee']} | {truncate(r['summary'])} |"
            )
        lines.append("")

    table("Not updated this week", data["stale"])
    table("Updated this week", data["fresh"])

    if data["missing_architect"]:
        lines.append("**Architect unset:** " + ", ".join(data["missing_architect"]))
        lines.append("")

    if data.get("no_contact"):
        lines.append(
            "**No architect or assignee (email skipped):** "
            + ", ".join(data["no_contact"])
        )
        lines.append("")

    if include_email_offer and data["stale_count"] > 0:
        n_drafts = len(data.get("email_drafts", []))
        lines.append("## Follow-up emails")
        lines.append("")
        if n_drafts:
            lines.append(
                f"**{n_drafts} draft email(s)** can go to architects "
                f"(or assignees when architect is unset). "
                f"Run with `--email-drafts` to print full drafts, or ask the agent to prepare them."
            )
        else:
            lines.append(
                "_No recipients — stale items lack both architect and assignee._"
            )
        lines.append("")

    return "\n".join(lines)


def markdown_email_drafts(data: dict) -> str:
    drafts = data.get("email_drafts", [])
    if not data["stale"]:
        return "_No stale items — no follow-up emails needed._\n"
    if not drafts:
        return (
            "_Stale items exist but none have an architect or assignee to email._\n"
            f"No contact: {', '.join(data.get('no_contact', [])) or 'n/a'}\n"
        )

    lines = [
        "# VirtShortList follow-up email drafts",
        "",
        "_Recipients: **Architect** when set; otherwise **Assignee**. "
        "One email per person covering all their stale items._",
        "",
    ]

    for i, d in enumerate(drafts, 1):
        role = "Architect" if d["contact_role"] == "architect" else "Assignee"
        to_line = d["to_email"] or "(email not in Jira — look up in directory)"
        lines.append(f"## Email {i}: {d['to_name']} ({role})")
        lines.append("")
        lines.append(f"**To:** {to_line}")
        lines.append(f"**Subject:** {d['subject']}")
        lines.append("")
        lines.append("```")
        lines.append(d["body"])
        lines.append("```")
        lines.append("")
        if d["mailto"]:
            lines.append(f"[Open in mail client]({d['mailto']})")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="VirtShortList Features/Outcomes report")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env_jira"),
        help="Env file with JIRA_URL, JIRA_API_TOKEN, JIRA_USERNAME (default: .env_jira)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown")
    parser.add_argument(
        "--email-drafts",
        action="store_true",
        help="Print follow-up email drafts for stale items (architect, else assignee)",
    )
    parser.add_argument(
        "--with-email",
        action="store_true",
        help="Print report and email drafts together",
    )
    args = parser.parse_args()

    load_env_file(args.env_file)
    base_url, auth = jira_config()
    os.environ.setdefault("JIRA_URL", base_url)

    try:
        data = fetch_report(base_url, auth)
    except requests.HTTPError as e:
        print(f"Jira API error: {e}", file=sys.stderr)
        if e.response is not None:
            print(e.response.text[:500], file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(data, indent=2))
    elif args.email_drafts:
        print(markdown_email_drafts(data))
    elif args.with_email:
        print(markdown_report(data))
        print()
        print(markdown_email_drafts(data))
    else:
        print(markdown_report(data))


if __name__ == "__main__":
    main()
