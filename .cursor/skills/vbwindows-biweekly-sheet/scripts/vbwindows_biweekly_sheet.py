#!/usr/bin/env python3
"""
VBWindows biweekly executive brief → Google Sheet tab.

fetch   — pull label=VBWindows activity for a 2-week window ending on --end-date
publish — create a NEW sheet tab and write briefs (caller must fill exec_brief)

Uses the running user's Jira env (.env_jira) and Google gws auth — never hardcode
another person's credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

COLOR_STATUS_FIELD = "customfield_10712"
STATUS_SUMMARY_FIELD = "customfield_10814"
DEFAULT_JQL = "labels = VBWindows ORDER BY key ASC"
DEFAULT_SHEET_ID = "12NsWug2zDvtd1_ry9cZBFM_Fgv4fM7yBZND0PudMCoU"
KEEP_CHANGELOG_FIELDS = {
    "status",
    "Status",
    "assignee",
    "Assignee",
    "resolution",
    "Resolution",
    "Fix Version",
    "priority",
    "Priority",
    "Link",
    "Parent",
    "summary",
    "Summary",
    "Issue Type",
    "Components",
    "Component",
    "labels",
    "Due Date",
    "duedate",
    "Target start",
    "Target end",
}
COLOR_TOKENS = {
    "Red": {
        "bg": {"red": 0.788, "green": 0.098, "blue": 0.043},
        "fg": {"red": 1, "green": 1, "blue": 1},
    },
    "Yellow": {
        "bg": {"red": 0.941, "green": 0.753, "blue": 0.0},
        "fg": {"red": 0.09, "green": 0.09, "blue": 0.09},
    },
    "Green": {
        "bg": {"red": 0.231, "green": 0.502, "blue": 0.173},
        "fg": {"red": 1, "green": 1, "blue": 1},
    },
    "Unset": {
        "bg": {"red": 0.878, "green": 0.878, "blue": 0.878},
        "fg": {"red": 0.3, "green": 0.3, "blue": 0.3},
    },
}


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


def resolve_env_file(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            print(f"Error: --env-file not found: {p}", file=sys.stderr)
            sys.exit(1)
        return p
    root = Path.cwd()
    # Prefer the caller's personal .env_jira only — never auto-pick another user's file.
    for name in (".env_jira",):
        cand = root / name
        if cand.is_file():
            return cand
    return None


def jira_user() -> str:
    user = os.environ.get("JIRA_USERNAME") or os.environ.get("JIRA_EMAIL")
    if not user:
        print("Error: set JIRA_USERNAME or JIRA_EMAIL (your login).", file=sys.stderr)
        sys.exit(1)
    return user


def jira_config() -> tuple[str, HTTPBasicAuth]:
    url = os.environ.get("JIRA_URL", "").rstrip("/")
    token = os.environ.get("JIRA_API_TOKEN", "")
    missing = [k for k, v in (("JIRA_URL", url), ("JIRA_API_TOKEN", token)) if not v]
    if missing:
        print(f"Error: missing {', '.join(missing)}.", file=sys.stderr)
        print(
            "Copy .cursor/skills/vbwindows-biweekly-sheet/env.jira.example "
            "to .env_jira with YOUR credentials.",
            file=sys.stderr,
        )
        sys.exit(1)
    return url, HTTPBasicAuth(jira_user(), token)


def parse_end_date(s: str) -> date:
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        print("Error: --end-date must be YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)


def window_bounds(end: date) -> tuple[datetime, datetime]:
    """Inclusive window: end-date and the 14 calendar days before it (15 days total)."""
    start = end - timedelta(days=14)
    start_dt = datetime(start.year, start.month, start.day, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)
    return start_dt, end_dt


def tab_title_for_end(end: date) -> str:
    return end.strftime("%m%d%Y")


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.replace("Z", "+0000")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s, fmt).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def adf_to_text(node) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(x) for x in node)
    if not isinstance(node, dict):
        return str(node)
    t = node.get("type")
    if t == "text":
        return node.get("text", "")
    if t in ("paragraph", "heading", "blockquote", "listItem"):
        return adf_to_text(node.get("content", [])) + "\n"
    if t in (
        "bulletList",
        "orderedList",
        "doc",
        "panel",
        "expand",
        "table",
        "tableRow",
        "tableCell",
        "tableHeader",
    ):
        return adf_to_text(node.get("content", []))
    if t == "hardBreak":
        return "\n"
    if t == "mention":
        attrs = node.get("attrs") or {}
        return attrs.get("text") or ("@" + str(attrs.get("id", "")))
    return adf_to_text(node.get("content", []))


def color_status_value(raw, labels: list[str] | None) -> str:
    color = None
    if isinstance(raw, dict):
        color = raw.get("value") or raw.get("name")
    elif isinstance(raw, str) and raw.strip():
        color = raw.strip()
    if not color and labels:
        for lab, mapped in (
            ("health-red", "Red"),
            ("health-yellow", "Yellow"),
            ("health-green", "Green"),
        ):
            if lab in labels:
                color = mapped
                break
    return color or "Unset"


def suggest_theme(key: str) -> str:
    prefix = key.split("-", 1)[0]
    return {
        "VIRTCE": "BSOD / Fast-track",
        "RHEL": "tlbflush / Driver Verifier",
        "CGQE": "Chaos / drivers",
        "CNV": "Chaos / drivers",
        "TUSC": "Chaos / drivers",
        "EPMB": "Partner / KCS / Autopilot",
        "KCSOPP": "Partner / KCS / Autopilot",
        "VIRTSTRAT": "Partner / KCS / Autopilot",
        "HPSTRAT": "Partner / KCS / Autopilot",
    }.get(prefix, "Other")


def search_issues(base_url: str, auth: HTTPBasicAuth, jql: str, fields: list[str]) -> list[dict]:
    issues: list[dict] = []
    next_token = None
    while True:
        payload: dict = {"jql": jql, "maxResults": 50, "fields": fields}
        if next_token:
            payload["nextPageToken"] = next_token
        r = requests.post(f"{base_url}/rest/api/3/search/jql", json=payload, auth=auth, timeout=120)
        if r.status_code == 404:
            r = requests.get(
                f"{base_url}/rest/api/3/search",
                params={
                    "jql": jql,
                    "maxResults": 50,
                    "startAt": len(issues),
                    "fields": ",".join(fields),
                },
                auth=auth,
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            batch = data.get("issues") or []
            issues.extend(batch)
            if len(issues) >= data.get("total", 0) or not batch:
                break
            continue
        r.raise_for_status()
        data = r.json()
        batch = data.get("issues") or []
        issues.extend(batch)
        next_token = data.get("nextPageToken")
        if not next_token or not batch:
            break
    return issues


def fetch_changelog(base_url: str, auth: HTTPBasicAuth, key: str) -> list[dict]:
    out: list[dict] = []
    start_at = 0
    while True:
        r = requests.get(
            f"{base_url}/rest/api/3/issue/{key}/changelog",
            params={"startAt": start_at, "maxResults": 100},
            auth=auth,
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("values") or [])
        if start_at + data.get("maxResults", 100) >= data.get("total", 0):
            break
        start_at += data.get("maxResults", 100)
    return out


def cmd_fetch(args: argparse.Namespace) -> None:
    end = parse_end_date(args.end_date)
    start_dt, end_dt = window_bounds(end)
    base_url, auth = jira_config()

    # Verify acting user (must be the person running the skill)
    me = requests.get(f"{base_url}/rest/api/3/myself", auth=auth, timeout=60)
    me.raise_for_status()
    me_json = me.json()
    acting = me_json.get("emailAddress") or me_json.get("displayName")
    print(f"Jira acting user: {acting}", file=sys.stderr)

    fields = [
        "summary",
        "status",
        "assignee",
        "updated",
        "created",
        "issuetype",
        "priority",
        "labels",
        "comment",
        "resolution",
        COLOR_STATUS_FIELD,
        STATUS_SUMMARY_FIELD,
    ]
    issues = search_issues(base_url, auth, args.jql, fields)
    print(f"Found {len(issues)} issues ({start_dt.date()} → {end_dt.date()})", file=sys.stderr)

    items = []
    for iss in issues:
        key = iss["key"]
        f = iss["fields"]
        labels = f.get("labels") or []
        color = color_status_value(f.get(COLOR_STATUS_FIELD), labels)
        status_summary = adf_to_text(f.get(STATUS_SUMMARY_FIELD)).strip()

        win_comments = []
        for c in (f.get("comment") or {}).get("comments") or []:
            dt = parse_dt(c.get("created"))
            if not dt or not (start_dt <= dt <= end_dt):
                continue
            win_comments.append(
                {
                    "when": dt.isoformat(),
                    "author": (c.get("author") or {}).get("displayName", ""),
                    "body": adf_to_text(c.get("body")).strip()[:4000],
                }
            )

        win_changes = []
        for hist in fetch_changelog(base_url, auth, key):
            dt = parse_dt(hist.get("created"))
            if not dt or not (start_dt <= dt <= end_dt):
                continue
            author = (hist.get("author") or {}).get("displayName", "")
            for item in hist.get("items") or []:
                field = item.get("field")
                if field not in KEEP_CHANGELOG_FIELDS:
                    continue
                win_changes.append(
                    {
                        "when": dt.isoformat(),
                        "author": author,
                        "field": field,
                        "from": item.get("fromString"),
                        "to": item.get("toString"),
                    }
                )

        created = parse_dt(f.get("created"))
        source_bits = []
        if status_summary:
            source_bits.append(f"Status Summary:\n{status_summary}")
        if win_comments:
            source_bits.append(
                "Comments in window:\n"
                + "\n---\n".join(
                    f"{c['when'][:10]} [{c['author']}]\n{c['body']}" for c in win_comments
                )
            )
        if win_changes:
            source_bits.append(
                "Changelog in window:\n"
                + "\n".join(
                    f"{c['when'][:10]} [{c['author']}] {c['field']}: "
                    f"{c['from']!r} → {c['to']!r}"
                    for c in win_changes[:40]
                )
            )

        items.append(
            {
                "key": key,
                "summary": f.get("summary") or "",
                "status": (f.get("status") or {}).get("name") or "",
                "assignee": ((f.get("assignee") or {}).get("displayName")) or "",
                "color_status": color,
                "theme": suggest_theme(key),
                "url": f"{base_url}/browse/{key}",
                "created_in_window": bool(created and start_dt <= created <= end_dt),
                "source_text": "\n\n".join(source_bits).strip(),
                "exec_brief": "",
                "comments": win_comments,
                "changelog": win_changes,
            }
        )

    payload = {
        "end_date": end.isoformat(),
        "window_start": start_dt.date().isoformat(),
        "window_end": end_dt.date().isoformat(),
        "tab_title_base": tab_title_for_end(end),
        "jira_user": acting,
        "jql": args.jql,
        "spreadsheet_id": os.environ.get("VBWINDOWS_SHEET_ID", DEFAULT_SHEET_ID),
        "items": items,
    }

    out = Path(args.out) if args.out else Path(f"vbwindows_briefs_{end.isoformat()}.json")
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {out} ({len(items)} items). Fill exec_brief on each item, then publish.")


def google_access_token() -> str:
    """Use the logged-in gws user's refresh token (whoever ran `gws auth login`)."""
    try:
        exp = subprocess.check_output(
            ["gws", "auth", "export", "--unmasked"], text=True, stderr=subprocess.STDOUT
        )
    except FileNotFoundError:
        print("Error: gws CLI not found. Install Google Workspace CLI.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(e.output, file=sys.stderr)
        print(
            "Error: gws auth failed. Run: gws auth login -s sheets,drive\n"
            "Use YOUR Google account (the person running this skill).",
            file=sys.stderr,
        )
        sys.exit(1)

    start = exp.find("{")
    if start < 0:
        print("Error: unexpected gws auth export output", file=sys.stderr)
        sys.exit(1)
    creds = json.loads(exp[start:])
    cs_path = Path.home() / ".config/gws/client_secret.json"
    if not cs_path.is_file():
        print(f"Error: missing {cs_path}", file=sys.stderr)
        sys.exit(1)
    cs = json.loads(cs_path.read_text())
    installed = cs.get("installed") or cs.get("web") or cs
    data = urllib.parse.urlencode(
        {
            "client_id": installed["client_id"],
            "client_secret": installed["client_secret"],
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            tok = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(e.read().decode(), file=sys.stderr)
        print(
            "Error refreshing Google token. Re-run: gws auth login -s sheets,drive",
            file=sys.stderr,
        )
        sys.exit(1)
    return tok["access_token"]


def sheets_api(access: str, spreadsheet_id: str, method: str, path: str, body=None, params=None):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Authorization": f"Bearer {access}", "Content-Type": "application/json"}
    data_b = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data_b, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Sheets API HTTP {e.code}: {e.read().decode()}")


def unique_tab_title(existing: set[str], base: str) -> str:
    if base not in existing:
        return base
    n = 2
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


def cmd_publish(args: argparse.Namespace) -> None:
    briefs_path = Path(args.briefs)
    if not briefs_path.is_file():
        print(f"Error: briefs file not found: {briefs_path}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(briefs_path.read_text())
    items = data.get("items") or []
    missing = [i["key"] for i in items if not (i.get("exec_brief") or "").strip()]
    if missing and not args.allow_empty_briefs:
        print(
            "Error: exec_brief empty for: " + ", ".join(missing),
            file=sys.stderr,
        )
        print("Agent must fill executive briefs before publish.", file=sys.stderr)
        sys.exit(1)

    end = parse_end_date(data.get("end_date") or args.end_date or "")
    start = data.get("window_start") or (end - timedelta(days=14)).isoformat()
    end_s = data.get("window_end") or end.isoformat()
    base_title = data.get("tab_title_base") or tab_title_for_end(end)
    spreadsheet_id = (
        args.spreadsheet_id
        or os.environ.get("VBWINDOWS_SHEET_ID")
        or data.get("spreadsheet_id")
        or DEFAULT_SHEET_ID
    )

    access = google_access_token()
    # Best-effort identity check via tokeninfo
    try:
        with urllib.request.urlopen(
            f"https://oauth2.googleapis.com/tokeninfo?access_token={urllib.parse.quote(access)}"
        ) as resp:
            info = json.loads(resp.read())
            print(
                f"Google acting user: {info.get('email') or info.get('sub')}",
                file=sys.stderr,
            )
    except Exception:
        print("Google acting user: (logged-in gws session)", file=sys.stderr)

    meta = sheets_api(
        access,
        spreadsheet_id,
        "GET",
        "",
        params={"fields": "properties.title,sheets.properties"},
    )
    existing = {s["properties"]["title"] for s in meta.get("sheets") or []}
    title = unique_tab_title(existing, base_title)
    if title != base_title:
        print(f"Tab {base_title!r} exists — creating {title!r}", file=sys.stderr)

    if args.dry_run:
        print(f"[dry-run] would create tab {title!r} on {spreadsheet_id} with {len(items)} rows")
        return

    resp = sheets_api(
        access,
        spreadsheet_id,
        "POST",
        ":batchUpdate",
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {
                            "title": title,
                            "gridProperties": {
                                "frozenRowCount": 1,
                                "columnCount": 7,
                                "rowCount": max(50, len(items) + 5),
                            },
                        }
                    }
                }
            ]
        },
    )
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]

    header = [
        "Key",
        "Summary",
        "Status",
        "Color Status",
        "Assignee",
        "Theme",
        "Executive Brief",
    ]
    rows = [header]
    for it in items:
        key = it["key"]
        url = it.get("url") or f"https://redhat.atlassian.net/browse/{key}"
        rows.append(
            [
                f'=HYPERLINK("{url}","{key}")',
                it.get("summary") or "",
                it.get("status") or "",
                it.get("color_status") or "Unset",
                it.get("assignee") or "",
                it.get("theme") or "",
                (it.get("exec_brief") or "").strip(),
            ]
        )

    range_name = f"'{title}'!A1"
    put_url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
        f"{urllib.parse.quote(range_name, safe='')}?valueInputOption=USER_ENTERED"
    )
    body = json.dumps(
        {"range": range_name, "majorDimension": "ROWS", "values": rows}
    ).encode()
    req = urllib.request.Request(
        put_url,
        data=body,
        headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"Wrote {json.loads(resp.read()).get('updatedCells')} cells", file=sys.stderr)

    format_reqs: list[dict] = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.15, "green": 0.15, "blue": 0.15},
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                        },
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {"pixelSize": 120},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 1,
                    "endIndex": 2,
                },
                "properties": {"pixelSize": 280},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 2,
                    "endIndex": 3,
                },
                "properties": {"pixelSize": 110},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 3,
                    "endIndex": 4,
                },
                "properties": {"pixelSize": 110},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 4,
                    "endIndex": 5,
                },
                "properties": {"pixelSize": 160},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 5,
                    "endIndex": 6,
                },
                "properties": {"pixelSize": 170},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 6,
                    "endIndex": 7,
                },
                "properties": {"pixelSize": 520},
                "fields": "pixelSize",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": len(rows),
                    "startColumnIndex": 6,
                    "endColumnIndex": 7,
                },
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP",
                        "verticalAlignment": "TOP",
                    }
                },
                "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 1,
                    "endIndex": len(rows),
                },
                "properties": {"pixelSize": 72},
                "fields": "pixelSize",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 3,
                    "endColumnIndex": 4,
                },
                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat.horizontalAlignment",
            }
        },
    ]

    for i, row in enumerate(rows[1:], start=1):
        color_val = row[3] if len(row) > 3 else "Unset"
        token = COLOR_TOKENS.get(color_val, COLOR_TOKENS["Unset"])
        format_reqs.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": i,
                        "endRowIndex": i + 1,
                        "startColumnIndex": 3,
                        "endColumnIndex": 4,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": token["bg"],
                            "textFormat": {
                                "bold": True,
                                "foregroundColor": token["fg"],
                            },
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
                }
            }
        )

    sheets_api(access, spreadsheet_id, "POST", ":batchUpdate", body={"requests": format_reqs})

    link = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet_id}"
    print(json.dumps({"tab": title, "sheet_id": sheet_id, "url": link, "window": f"{start} → {end_s}"}))
    print(link)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="VBWindows biweekly brief → Google Sheet")
    p.add_argument(
        "--env-file",
        help="Path to personal Jira env file (default: ./.env_jira only)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="Fetch VBWindows activity for the 2-week window")
    f.add_argument(
        "--end-date",
        required=True,
        help="End date of the 2-week period (YYYY-MM-DD), inclusive",
    )
    f.add_argument("--out", help="Output JSON path")
    f.add_argument("--jql", default=DEFAULT_JQL)
    f.set_defaults(func=cmd_fetch)

    pub = sub.add_parser("publish", help="Create a NEW sheet tab and write briefs")
    pub.add_argument("--briefs", required=True, help="JSON from fetch with exec_brief filled")
    pub.add_argument("--end-date", help="Override end date if missing from JSON")
    pub.add_argument("--spreadsheet-id", help="Override spreadsheet ID")
    pub.add_argument("--dry-run", action="store_true")
    pub.add_argument(
        "--allow-empty-briefs",
        action="store_true",
        help="Allow publish when some exec_brief fields are empty",
    )
    pub.set_defaults(func=cmd_publish)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    env_path = resolve_env_file(args.env_file)
    if env_path:
        load_env_file(env_path)
        print(f"Loaded env: {env_path}", file=sys.stderr)
    elif args.cmd == "fetch" and not (
        os.environ.get("JIRA_URL") and os.environ.get("JIRA_API_TOKEN")
    ):
        print(
            "Error: no .env_jira found. Copy env.jira.example to .env_jira "
            "with YOUR Jira credentials (do not use another person's file).",
            file=sys.stderr,
        )
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
