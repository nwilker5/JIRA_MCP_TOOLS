#!/usr/bin/env python3
"""
CNV epic hygiene report per Development Process:
https://redhat.atlassian.net/wiki/spaces/cnv/pages/268599631/Development+Process

Finds open CNV epics missing components and/or a VIRTSTRAT Feature parent.

Requires JIRA_URL, JIRA_API_TOKEN, and JIRA_USERNAME or JIRA_EMAIL.
Use .env_jira (copy from env.jira.example) — each team member uses their own token.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests
from requests.auth import HTTPBasicAuth

BROWSE = "https://redhat.atlassian.net/browse"
EPIC_TEMPLATE_KEY = "CNV-4600"
RELEASE_CHECKLIST_LABEL = "CNV-Release-Checklist"
NO_PARENT = "—"

BASE_JQL = (
    "project = CNV AND issuetype = Epic AND status != Closed "
    "AND component is EMPTY ORDER BY key ASC"
)
SEARCH_FIELDS = ["summary", "status", "assignee", "parent", "fixVersions", "labels"]


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


def search_all(base_url: str, auth: HTTPBasicAuth, jql: str, fields: list[str]) -> list[dict]:
    url = f"{base_url}/rest/api/3/search/jql"
    all_issues: list[dict] = []
    token = None
    while True:
        payload: dict = {"jql": jql, "maxResults": 100, "fields": fields}
        if token:
            payload["nextPageToken"] = token
        r = requests.post(url, json=payload, auth=auth, timeout=120)
        r.raise_for_status()
        data = r.json()
        all_issues.extend(data.get("issues", []))
        token = data.get("nextPageToken")
        if not token:
            break
    return all_issues


def get_parent_info(
    base_url: str, auth: HTTPBasicAuth, parent_key: str, cache: dict
) -> dict:
    if parent_key in cache:
        return cache[parent_key]
    r = requests.get(
        f"{base_url}/rest/api/3/issue/{parent_key}",
        auth=auth,
        params={"fields": "issuetype,summary,status"},
        timeout=60,
    )
    r.raise_for_status()
    f = r.json()["fields"]
    info = {
        "key": parent_key,
        "type": f["issuetype"]["name"],
        "summary": f.get("summary", ""),
        "status": f["status"]["name"],
        "is_feature": f["issuetype"]["name"] == "Feature",
    }
    cache[parent_key] = info
    return info


def parse_epic(issue: dict, base_url: str, auth: HTTPBasicAuth, cache: dict) -> dict:
    f = issue["fields"]
    parent_field = f.get("parent")
    if parent_field:
        pinfo = get_parent_info(base_url, auth, parent_field["key"], cache)
        parent_key = pinfo["key"]
        parent_type = pinfo["type"]
        parent_summary = pinfo["summary"]
        has_feature_parent = pinfo["is_feature"]
    else:
        parent_key = None
        parent_type = None
        parent_summary = None
        has_feature_parent = False

    assignee = f.get("assignee")
    fix_versions = ", ".join(v["name"] for v in (f.get("fixVersions") or [])) or NO_PARENT
    labels = f.get("labels") or []

    return {
        "key": issue["key"],
        "summary": f.get("summary", ""),
        "status": f["status"]["name"],
        "assignee": assignee["displayName"] if assignee else "(unassigned)",
        "fix_versions": fix_versions,
        "labels": labels,
        "parent_key": parent_key,
        "parent_type": parent_type,
        "parent_summary": parent_summary,
        "has_feature_parent": has_feature_parent,
        "url": f"{BROWSE}/{issue['key']}",
        "is_template": issue["key"] == EPIC_TEMPLATE_KEY,
        "is_release_checklist": RELEASE_CHECKLIST_LABEL in labels,
    }


def apply_excludes(
    rows: list[dict],
    *,
    exclude_template: bool,
    exclude_release_checklist: bool,
    exclude_keys: set[str],
) -> list[dict]:
    out = []
    for row in rows:
        if exclude_template and row["is_template"]:
            continue
        if exclude_release_checklist and row["is_release_checklist"]:
            continue
        if row["key"] in exclude_keys:
            continue
        out.append(row)
    return out


def bulk_jira_url(keys: list[str]) -> str:
    if not keys:
        return ""
    encoded = quote(",".join(keys))
    return f"https://redhat.atlassian.net/issues/?jql=key%20in%20({encoded})"


def fetch_report(
    base_url: str,
    auth: HTTPBasicAuth,
    *,
    exclude_template: bool,
    exclude_release_checklist: bool,
    exclude_keys: set[str],
) -> dict:
    issues = search_all(base_url, auth, BASE_JQL, SEARCH_FIELDS)
    cache: dict = {}
    parsed = [parse_epic(i, base_url, auth, cache) for i in issues]

    no_component_all = parsed
    missing_both = [r for r in parsed if not r["has_feature_parent"]]
    missing_component_only = [r for r in parsed if r["has_feature_parent"]]

    missing_both_filtered = apply_excludes(
        missing_both,
        exclude_template=exclude_template,
        exclude_release_checklist=exclude_release_checklist,
        exclude_keys=exclude_keys,
    )
    missing_component_filtered = apply_excludes(
        missing_component_only,
        exclude_template=exclude_template,
        exclude_release_checklist=exclude_release_checklist,
        exclude_keys=exclude_keys,
    )

    excluded = len(missing_both) - len(missing_both_filtered)

    return {
        "reference_url": (
            "https://redhat.atlassian.net/wiki/spaces/cnv/pages/268599631/Development+Process"
        ),
        "jql_no_component": BASE_JQL,
        "total_open_no_component": len(no_component_all),
        "missing_component_and_feature_parent": missing_both_filtered,
        "missing_component_has_feature_parent": missing_component_filtered,
        "excluded_from_primary_count": excluded,
        "bulk_url_primary": bulk_jira_url([r["key"] for r in missing_both_filtered]),
    }


def truncate(text: str, n: int = 50) -> str:
    if not text:
        return ""
    return text if len(text) <= n else text[: n - 1] + "…"


def row_table(title: str, rows: list[dict], *, show_parent: bool = True) -> list[str]:
    lines = [f"## {title} ({len(rows)})", ""]
    if not rows:
        lines.extend(["_None._", ""])
        return lines

    if show_parent:
        lines.append(
            "| Key | Status | Assignee | Fix version | Parent | Parent type | Summary |"
        )
        lines.append(
            "|-----|--------|----------|-------------|--------|-------------|---------|"
        )
        for r in rows:
            key = f"[{r['key']}]({r['url']})"
            parent = r["parent_key"] or NO_PARENT
            ptype = r["parent_type"] or NO_PARENT
            lines.append(
                f"| {key} | {r['status']} | {r['assignee']} | {r['fix_versions']} | "
                f"{parent} | {ptype} | {truncate(r['summary'])} |"
            )
    else:
        lines.append("| Key | Status | Assignee | Feature parent | Summary |")
        lines.append("|-----|--------|----------|----------------|---------|")
        for r in rows:
            key = f"[{r['key']}]({r['url']})"
            parent = r["parent_key"] or NO_PARENT
            lines.append(
                f"| {key} | {r['status']} | {r['assignee']} | {parent} | "
                f"{truncate(r['summary'])} |"
            )
    lines.append("")
    return lines


def markdown_report(data: dict) -> str:
    primary = data["missing_component_and_feature_parent"]
    secondary = data["missing_component_has_feature_parent"]
    lines = [
        "# CNV epic hygiene report",
        "",
        f"Per [CNV Development Process]({data['reference_url']}): open epics need "
        "**components** and a **Feature** parent (VIRTSTRAT).",
        "",
        "## Summary",
        "",
        f"- **Open epics with no component:** {data['total_open_no_component']}",
        f"- **No component and no Feature parent:** {len(primary)}",
        f"- **No component but Feature parent is set:** {len(secondary)}",
    ]
    if data["excluded_from_primary_count"]:
        lines.append(
            f"- **Excluded from primary table (filters):** {data['excluded_from_primary_count']}"
        )
    lines.extend(
        [
            "",
            f"JQL (component check): `{data['jql_no_component']}`",
            "",
            "_Parent issuetype is resolved via API (Feature vs Initiative, Feature Request, etc.)._",
            "",
        ]
    )
    lines.extend(row_table("No component and no Feature parent", primary))
    lines.extend(
        row_table("No component — Feature parent OK (still need component)", secondary, show_parent=False)
    )

    wrong_parent = [
        r for r in primary if r["parent_key"] and not r["has_feature_parent"]
    ]
    if wrong_parent:
        lines.append("### Non-Feature parents (subset of primary table)")
        lines.append("")
        for r in wrong_parent:
            lines.append(
                f"- **{r['key']}** → {r['parent_key']} ({r['parent_type']}): "
                f"{truncate(r['parent_summary'], 70)}"
            )
        lines.append("")

    if data["bulk_url_primary"]:
        lines.append("## Open all primary violations in Jira")
        lines.append("")
        lines.append(data["bulk_url_primary"])
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CNV epic hygiene: missing components and/or Feature parent"
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env_jira"),
        help="Env file with JIRA_* credentials (default: .env_jira)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown")
    parser.add_argument(
        "--exclude-template",
        action="store_true",
        help=f"Exclude {EPIC_TEMPLATE_KEY} from results",
    )
    parser.add_argument(
        "--exclude-release-checklist",
        action="store_true",
        help=f"Exclude epics with label {RELEASE_CHECKLIST_LABEL}",
    )
    parser.add_argument(
        "--exclude-key",
        action="append",
        default=[],
        metavar="CNV-123",
        help="Exclude additional issue key (repeatable)",
    )
    args = parser.parse_args()

    load_env_file(args.env_file)
    base_url, auth = jira_config()

    exclude_keys = {k.upper() for k in args.exclude_key}

    try:
        data = fetch_report(
            base_url,
            auth,
            exclude_template=args.exclude_template,
            exclude_release_checklist=args.exclude_release_checklist,
            exclude_keys=exclude_keys,
        )
    except requests.HTTPError as e:
        print(f"Jira API error: {e}", file=sys.stderr)
        if e.response is not None:
            print(e.response.text[:500], file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(markdown_report(data))


if __name__ == "__main__":
    main()
