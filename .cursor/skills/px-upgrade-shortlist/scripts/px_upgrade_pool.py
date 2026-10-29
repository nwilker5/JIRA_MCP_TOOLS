#!/usr/bin/env python3
"""
Fetch unresolved CNV/MTV issues with PX Impact Score that mention upgrade.

Returns the raw pool for agent curation (OCP vs CNV vs both vs unclear).
Readable PX Impact Score comes from renderedFields (customfield_11003).

Requires JIRA_URL, JIRA_API_TOKEN, and JIRA_USERNAME or JIRA_EMAIL.
Use .env_jira (copy from env.jira.example) — each team member uses their own token.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

BROWSE = "https://redhat.atlassian.net/browse"
PX_SCORE_FIELD = "customfield_11003"

JQL = (
    'project in (CNV, MTV) '
    "AND resolution = Unresolved "
    'AND "PX Impact Score" is not EMPTY '
    'AND text ~ "upgrade" '
    'ORDER BY "PX Impact Score" DESC'
)

SEARCH_FIELDS = [
    "summary",
    "status",
    "issuetype",
    "description",
    "labels",
    "components",
    "updated",
    "created",
    PX_SCORE_FIELD,
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
        print("Copy env.jira.example to .env_jira and add credentials.", file=sys.stderr)
        sys.exit(1)
    return url, HTTPBasicAuth(jira_user(), token)


def jira_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def walk_adf(node) -> str:
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text") or ""
        return " ".join(
            filter(None, (walk_adf(c) for c in node.get("content", []) or []))
        )
    if isinstance(node, list):
        return " ".join(filter(None, (walk_adf(x) for x in node)))
    return ""


def flatten_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    return " ".join(walk_adf(value).split())


def parse_score(rendered: str | None) -> int | None:
    if not rendered:
        return None
    try:
        return int(str(rendered).replace(",", "").strip())
    except ValueError:
        return None


def search_pool(base: str, auth: HTTPBasicAuth, session: requests.Session) -> list[dict]:
    out: list[dict] = []
    token = None
    while True:
        params: dict = {
            "jql": JQL,
            "maxResults": 50,
            "fields": ",".join(SEARCH_FIELDS),
        }
        if token:
            params["nextPageToken"] = token
        r = session.get(
            f"{base}/rest/api/3/search/jql",
            auth=auth,
            params=params,
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        for issue in data.get("issues") or []:
            out.append(issue)
        token = data.get("nextPageToken")
        if data.get("isLast", True):
            break
    return out


def enrich_issue(
    base: str, auth: HTTPBasicAuth, session: requests.Session, issue: dict
) -> dict:
    key = issue["key"]
    fields = issue.get("fields") or {}

    # Rendered PX Impact Score (numeric)
    ir = session.get(
        f"{base}/rest/api/3/issue/{key}",
        auth=auth,
        params={"fields": PX_SCORE_FIELD, "expand": "renderedFields"},
        timeout=60,
    )
    ir.raise_for_status()
    full = ir.json()
    rendered = (full.get("renderedFields") or {}).get(PX_SCORE_FIELD)
    score = parse_score(rendered)

    # Upgrade-related comments (newest first)
    cr = session.get(
        f"{base}/rest/api/3/issue/{key}/comment",
        auth=auth,
        params={"maxResults": 50, "orderBy": "-created"},
        timeout=60,
    )
    upgrade_comments: list[dict] = []
    if cr.status_code == 200:
        for c in cr.json().get("comments") or []:
            text = flatten_text(c.get("body"))
            if re.search(r"upgrad", text, re.I):
                upgrade_comments.append(
                    {
                        "created": c.get("created"),
                        "text": text[:600],
                    }
                )
            if len(upgrade_comments) >= 5:
                break

    return {
        "key": key,
        "url": f"{BROWSE}/{key}",
        "summary": fields.get("summary") or "",
        "status": (fields.get("status") or {}).get("name"),
        "issuetype": (fields.get("issuetype") or {}).get("name"),
        "labels": fields.get("labels") or [],
        "components": [c["name"] for c in (fields.get("components") or [])],
        "px_impact_score": score,
        "px_impact_score_raw": fields.get(PX_SCORE_FIELD),
        "updated": fields.get("updated"),
        "created": fields.get("created"),
        "description": flatten_text(fields.get("description"))[:2500],
        "upgrade_comments": upgrade_comments,
    }


def to_markdown(rows: list[dict]) -> str:
    lines = [
        f"# PX upgrade pool ({len(rows)} unresolved hits)",
        "",
        "Raw keyword pool — **not** the curated shortlist. Agent must read and classify.",
        "",
        f"JQL: `{JQL}`",
        "",
        "| PX Impact Score | Key | Type | Status | Summary |",
        "|---:|---|---|---|---|",
    ]
    for r in rows:
        score = r["px_impact_score"] if r["px_impact_score"] is not None else "—"
        lines.append(
            f"| {score} | [{r['key']}]({r['url']}) | {r['issuetype']} | "
            f"{r['status']} | {r['summary'].replace('|', '/')} |"
        )
    lines.append("")
    lines.append(
        "Next: curate per skill instructions (keep true upgrade-context only; "
        "classify OCP / CNV / Both / Unclear; rewrite impact lines; sort by score)."
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default=".env_jira",
        help="Path to env file (default: .env_jira in cwd)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of markdown",
    )
    args = parser.parse_args()

    load_env_file(Path(args.env_file))
    # Also try repo-root relative to this script
    script_root = Path(__file__).resolve().parents[3]
    load_env_file(script_root / ".env_jira")

    base, auth = jira_config()
    session = jira_session()

    issues = search_pool(base, auth, session)
    rows = [enrich_issue(base, auth, session, i) for i in issues]
    rows.sort(
        key=lambda r: (
            -(r["px_impact_score"] if r["px_impact_score"] is not None else -1),
            r["key"],
        )
    )

    if args.json:
        payload = {
            "jql": JQL,
            "pool_count": len(rows),
            "note": (
                "Raw keyword pool only. Curate per "
                ".cursor/skills/px-upgrade-shortlist/SKILL.md"
            ),
            "issues": rows,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(to_markdown(rows))


if __name__ == "__main__":
    main()
