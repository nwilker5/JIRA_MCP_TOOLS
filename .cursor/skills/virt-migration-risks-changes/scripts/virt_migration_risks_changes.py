#!/usr/bin/env python3
"""
Virt Migration Betterment: Risks — biweekly Changes tab.

draft  — read Sheet1's two newest Status date columns (read-only) → JSON
apply  — write ONLY the Changes tab: insert period column at C, shift older right,
         put TLDR Top 5 under that column

Never modifies Sheet1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

DEFAULT_SHEET_ID = "1pVYpmz4LMInpme4YPUexM1PaAiTBj376bcLTsMwj2MA"
SOURCE_TAB = "Sheet1"
CHANGES_TAB = "Changes"
HEADER_BG = {"red": 0.90, "green": 0.90, "blue": 0.90}
HEADER_FG = {"red": 0, "green": 0, "blue": 0}
LINK_BLUE = {"red": 0.06, "green": 0.46, "blue": 0.88}
STATUS_HEADER_RE = re.compile(r"^Status\s+(.+)$", re.I)


def google_access_token() -> str:
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
            "Error: gws auth failed. Run: gws auth login -s sheets,drive",
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
    data = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": f"Bearer {access}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        print(e.read().decode(), file=sys.stderr)
        raise


def print_google_user(access: str) -> None:
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


def parse_status_columns(header: list[str]) -> list[tuple[datetime, int, str]]:
    found: list[tuple[datetime, int, str]] = []
    for i, h in enumerate(header):
        m = STATUS_HEADER_RE.match((h or "").strip())
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1).strip(), "%B %d, %Y")
        except ValueError:
            continue
        found.append((d, i, h))
    found.sort(key=lambda t: t[0], reverse=True)
    return found


def period_header(old_d: datetime, new_d: datetime) -> str:
    return f"Changes {old_d.strftime('%b %-d')}–{new_d.strftime('%b %-d, %Y')}"


def col_letter(idx0: int) -> str:
    n = idx0 + 1
    letters = ""
    while n:
        n, r = divmod(n - 1, 26)
        letters = chr(65 + r) + letters
    return letters


def find_sheet(meta: dict, title: str) -> dict | None:
    for s in meta.get("sheets") or []:
        if s.get("properties", {}).get("title") == title:
            return s
    return None


def find_changes_sheet(meta: dict) -> dict | None:
    exact = find_sheet(meta, CHANGES_TAB)
    if exact:
        return exact
    for s in meta.get("sheets") or []:
        t = s.get("properties", {}).get("title") or ""
        if t.startswith("Changes"):
            return s
    return None


def read_values(access: str, spreadsheet_id: str, a1: str) -> list[list[str]]:
    rng = urllib.parse.quote(a1, safe="")
    data = sheets_api(access, spreadsheet_id, "GET", f"/values/{rng}")
    return data.get("values") or []


def write_values(access: str, spreadsheet_id: str, a1: str, values: list[list]) -> None:
    put_url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
        f"{urllib.parse.quote(a1, safe='')}?valueInputOption=USER_ENTERED"
    )
    body = json.dumps({"range": a1, "majorDimension": "ROWS", "values": values}).encode()
    req = urllib.request.Request(
        put_url,
        data=body,
        headers={
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"Wrote {json.loads(resp.read()).get('updatedCells')} cells → {a1}", file=sys.stderr)


def clear_range(access: str, spreadsheet_id: str, a1: str) -> None:
    clear_url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
        f"{urllib.parse.quote(a1, safe='')}:clear"
    )
    req = urllib.request.Request(
        clear_url,
        data=b"{}",
        headers={
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req):
        pass


def topic_key_from_cell(cell: str) -> str:
    """Strip HYPERLINK formula / display text to a plain topic key."""
    cell = (cell or "").strip()
    m = re.match(r'^=HYPERLINK\("[^"]*","(.*)"\)$', cell)
    if m:
        return m.group(1).replace('""', '"')
    return cell


def hyperlink_topic(spreadsheet_id: str, sheet1_gid: int, topic: str, row_1based: int) -> str:
    topic_esc = topic.replace('"', '""')
    link = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        f"#gid={sheet1_gid}&range=A{row_1based}"
    )
    return f'=HYPERLINK("{link}","{topic_esc}")'


def cmd_draft(args: argparse.Namespace) -> None:
    spreadsheet_id = (
        args.spreadsheet_id or os.environ.get("RISKS_SHEET_ID") or DEFAULT_SHEET_ID
    )
    access = google_access_token()
    print_google_user(access)

    meta = sheets_api(
        access,
        spreadsheet_id,
        "GET",
        "",
        params={"fields": "properties.title,sheets.properties"},
    )
    print(f"Spreadsheet: {meta.get('properties', {}).get('title')}", file=sys.stderr)
    src = find_sheet(meta, SOURCE_TAB)
    if not src:
        print(f"Error: source tab {SOURCE_TAB!r} not found", file=sys.stderr)
        sys.exit(1)
    sheet1_gid = src["properties"]["sheetId"]

    rows = read_values(access, spreadsheet_id, f"'{SOURCE_TAB}'!A1:Z500")
    if not rows:
        print("Error: Sheet1 is empty", file=sys.stderr)
        sys.exit(1)
    header = rows[0]
    status_cols = parse_status_columns(header)
    if len(status_cols) < 2:
        found = ", ".join(repr(h) for _, _, h in status_cols) or "(none)"
        print(
            "Error: need at least two columns titled like "
            f"'Status July 24, 2026' on Sheet1. Found: {found}",
            file=sys.stderr,
        )
        sys.exit(1)

    new_d, new_i, new_h = status_cols[0]
    old_d, old_i, old_h = status_cols[1]
    print(f"Comparing {new_h!r} vs {old_h!r}", file=sys.stderr)

    # Optional assignee column
    assignee_i = next((i for i, h in enumerate(header) if (h or "").strip().lower() == "assignee"), 2)

    items = []
    for row_1based, row in enumerate(rows[1:], start=2):
        width = max(new_i, old_i, assignee_i) + 1
        padded = list(row) + [""] * (width - len(row))
        topic = (padded[0] or "").strip()
        if not topic:
            continue
        newest = (padded[new_i] or "").strip()
        older = (padded[old_i] or "").strip()
        if newest == older:
            continue
        items.append(
            {
                "topic": topic,
                "sheet1_row": row_1based,
                "assignee": padded[assignee_i] if assignee_i < len(padded) else "",
                "status_new": newest,
                "status_old": older,
                "status_new_header": new_h,
                "status_old_header": old_h,
                "change": "",
            }
        )

    draft = {
        "spreadsheet_id": spreadsheet_id,
        "source_tab": SOURCE_TAB,
        "changes_tab": CHANGES_TAB,
        "sheet1_gid": sheet1_gid,
        "window_old": old_d.date().isoformat(),
        "window_new": new_d.date().isoformat(),
        "column_header": period_header(old_d, new_d),
        "status_new_header": new_h,
        "status_old_header": old_h,
        "items": items,
        "top_5_changes": ["", "", "", "", ""],
    }

    out = Path(args.out)
    out.write_text(json.dumps(draft, indent=2) + "\n")
    print(f"Wrote {out} ({len(items)} changed topics)", file=sys.stderr)
    print(out)


def ensure_changes_tab(
    access: str, spreadsheet_id: str, meta: dict
) -> tuple[int, str]:
    """Return (sheetId, title). Rename legacy 'Changes …' → Changes. Create if missing."""
    existing = find_changes_sheet(meta)
    if existing:
        sid = existing["properties"]["sheetId"]
        title = existing["properties"]["title"]
        if title != CHANGES_TAB:
            sheets_api(
                access,
                spreadsheet_id,
                "POST",
                ":batchUpdate",
                body={
                    "requests": [
                        {
                            "updateSheetProperties": {
                                "properties": {"sheetId": sid, "title": CHANGES_TAB},
                                "fields": "title",
                            }
                        }
                    ]
                },
            )
            print(f"Renamed {title!r} → {CHANGES_TAB!r}", file=sys.stderr)
        return sid, CHANGES_TAB

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
                            "title": CHANGES_TAB,
                            "gridProperties": {"rowCount": 200, "columnCount": 26},
                        }
                    }
                }
            ]
        },
    )
    sid = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"Created tab {CHANGES_TAB!r}", file=sys.stderr)
    return sid, CHANGES_TAB


def unmerge_all(access: str, spreadsheet_id: str, sheet_id: int) -> None:
    meta = sheets_api(
        access,
        spreadsheet_id,
        "GET",
        "",
        params={"fields": "sheets(properties(sheetId),merges)"},
    )
    reqs = []
    for s in meta.get("sheets") or []:
        if s["properties"]["sheetId"] != sheet_id:
            continue
        for mrg in s.get("merges") or []:
            rng = dict(mrg)
            rng["sheetId"] = sheet_id
            reqs.append({"unmergeCells": {"range": rng}})
    if reqs:
        sheets_api(access, spreadsheet_id, "POST", ":batchUpdate", body={"requests": reqs})


def cmd_apply(args: argparse.Namespace) -> None:
    draft_path = Path(args.draft)
    if not draft_path.is_file():
        print(f"Error: draft not found: {draft_path}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(draft_path.read_text())
    items = data.get("items") or []
    top5 = [str(x).strip() for x in (data.get("top_5_changes") or []) if str(x).strip()]
    if len(top5) < 5:
        print(
            f"Error: fill top_5_changes with exactly 5 bullets (have {len(top5)})",
            file=sys.stderr,
        )
        sys.exit(1)
    top5 = top5[:5]
    missing = [it["topic"] for it in items if not str(it.get("change") or "").strip()]
    if missing:
        print(
            "Error: empty change for: " + ", ".join(missing[:8])
            + ("…" if len(missing) > 8 else ""),
            file=sys.stderr,
        )
        sys.exit(1)

    spreadsheet_id = (
        args.spreadsheet_id
        or os.environ.get("RISKS_SHEET_ID")
        or data.get("spreadsheet_id")
        or DEFAULT_SHEET_ID
    )
    col_header = data.get("column_header") or "Changes"
    sheet1_gid = int(data.get("sheet1_gid") or 0)

    access = google_access_token()
    print_google_user(access)

    meta = sheets_api(
        access,
        spreadsheet_id,
        "GET",
        "",
        params={"fields": "properties.title,sheets(properties,merges)"},
    )
    # Refuse to touch anything but Changes
    src = find_sheet(meta, SOURCE_TAB)
    if src:
        sheet1_gid = src["properties"]["sheetId"]

    if args.dry_run:
        print(
            f"[dry-run] would insert column C {col_header!r} on {CHANGES_TAB!r} "
            f"with {len(items)} rows + Top 5 (Sheet1 untouched)"
        )
        return

    changes_id, changes_title = ensure_changes_tab(access, spreadsheet_id, meta)
    unmerge_all(access, spreadsheet_id, changes_id)

    # Re-read Changes after possible rename
    existing = read_values(access, spreadsheet_id, f"'{changes_title}'!A1:Z500")

    # Build topic → row map from existing (data rows only; stop before TLDR)
    existing_header = existing[0] if existing else []
    topic_to_row: dict[str, int] = {}  # topic -> 0-based row index in existing
    data_end = 0  # exclusive 0-based index of first blank / TLDR after header
    if existing:
        data_end = 1
        for i, row in enumerate(existing[1:], start=1):
            cell_a = row[0] if row else ""
            if not str(cell_a).strip():
                break
            if str(cell_a).strip().upper().startswith("TLDR"):
                break
            topic_to_row[topic_key_from_cell(str(cell_a))] = i
            data_end = i + 1

    # Detect existing period columns (C onward) — headers starting with Changes
    has_period_cols = False
    if existing_header and len(existing_header) >= 3:
        for h in existing_header[2:]:
            if (h or "").strip().lower().startswith("changes "):
                has_period_cols = True
                break
            if (h or "").strip().lower().startswith("what changed"):
                has_period_cols = True
                break

    # If first run (no usable Changes grid), bootstrap A/B + C
    bootstrap = not existing or not existing_header or data_end <= 1

    if bootstrap:
        grid = [["Topic", "Assignee", col_header]]
        for it in items:
            grid.append(
                [
                    hyperlink_topic(
                        spreadsheet_id, sheet1_gid, it["topic"], int(it["sheet1_row"])
                    ),
                    it.get("assignee") or "",
                    (it.get("change") or "").strip(),
                ]
            )
        clear_range(access, spreadsheet_id, f"'{changes_title}'!A1:Z500")
        write_values(access, spreadsheet_id, f"'{changes_title}'!A1", grid)
        n_data = len(grid)
        tldr_row_1based = n_data + 2
        tldr_block = [["TLDR — Top 5"]] + [[f"• {x}"] for x in top5]
        write_values(
            access,
            spreadsheet_id,
            f"'{changes_title}'!C{tldr_row_1based}",
            tldr_block,
        )
        _format_changes(
            access,
            spreadsheet_id,
            changes_id,
            n_data_rows=n_data,
            period_col_idx=2,
            tldr_row_0=tldr_row_1based - 1,
            top5_n=len(top5),
            n_period_cols=1,
        )
    else:
        # Insert a new column at index 2 (C); shift prior period columns right
        sheets_api(
            access,
            spreadsheet_id,
            "POST",
            ":batchUpdate",
            body={
                "requests": [
                    {
                        "insertDimension": {
                            "range": {
                                "sheetId": changes_id,
                                "dimension": "COLUMNS",
                                "startIndex": 2,
                                "endIndex": 3,
                            },
                            "inheritFromBefore": False,
                        }
                    }
                ]
            },
        )
        print(f"Inserted column C for {col_header!r}", file=sys.stderr)

        # Ensure Topic/Assignee header labels
        write_values(
            access,
            spreadsheet_id,
            f"'{changes_title}'!A1:C1",
            [["Topic", "Assignee", col_header]],
        )

        # Map draft items; add new topics as rows if needed
        change_by_topic = {
            it["topic"]: (it.get("change") or "").strip() for it in items
        }
        meta_by_topic = {it["topic"]: it for it in items}

        # Clear old TLDR block in former C (now D+) — wipe a band below data
        # Write per-row C values for known topics; append unknown topics
        col_c_values: list[list[str]] = []
        for topic, row_idx in sorted(topic_to_row.items(), key=lambda x: x[1]):
            col_c_values.append([change_by_topic.get(topic, "")])

        # Rows already exist — write C2:C{data_end}
        if topic_to_row:
            # Build aligned list in row order
            ordered: list[list[str]] = []
            max_row = max(topic_to_row.values())
            by_row = {r: t for t, r in topic_to_row.items()}
            for r in range(1, max_row + 1):
                t = by_row.get(r)
                ordered.append([change_by_topic.get(t, "") if t else ""])
            write_values(
                access,
                spreadsheet_id,
                f"'{changes_title}'!C2",
                ordered,
            )

        # Append topics not yet on Changes tab
        new_topics = [it for it in items if it["topic"] not in topic_to_row]
        append_start = data_end + 1  # 1-based
        if new_topics:
            append_rows = []
            for it in new_topics:
                append_rows.append(
                    [
                        hyperlink_topic(
                            spreadsheet_id,
                            sheet1_gid,
                            it["topic"],
                            int(it["sheet1_row"]),
                        ),
                        it.get("assignee") or "",
                        (it.get("change") or "").strip(),
                    ]
                )
            write_values(
                access,
                spreadsheet_id,
                f"'{changes_title}'!A{append_start}",
                append_rows,
            )
            data_end += len(new_topics)

        n_data = data_end  # includes header row count as data_end was exclusive → n_data rows total
        # data_end is exclusive 0-based after header count… after updates:
        # n_data = number of rows including header
        n_data = data_end  # 0-based exclusive index == count of rows if header at 0

        # Clear previous TLDR scraps below data across a wide range, then write Top 5 under C
        clear_range(
            access,
            spreadsheet_id,
            f"'{changes_title}'!A{n_data + 1}:Z{n_data + 40}",
        )
        tldr_row_1based = n_data + 2
        tldr_block = [["TLDR — Top 5"]] + [[f"• {x}"] for x in top5]
        write_values(
            access,
            spreadsheet_id,
            f"'{changes_title}'!C{tldr_row_1based}",
            tldr_block,
        )

        # Count period columns (C..) after insert
        refreshed = read_values(access, spreadsheet_id, f"'{changes_title}'!1:1")
        hdr = refreshed[0] if refreshed else []
        n_period = max(1, len(hdr) - 2)

        _format_changes(
            access,
            spreadsheet_id,
            changes_id,
            n_data_rows=n_data,
            period_col_idx=2,
            tldr_row_0=tldr_row_1based - 1,
            top5_n=len(top5),
            n_period_cols=n_period,
        )

    link = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={changes_id}"
    print(link)


def _format_changes(
    access: str,
    spreadsheet_id: str,
    sheet_id: int,
    *,
    n_data_rows: int,
    period_col_idx: int,
    tldr_row_0: int,
    top5_n: int,
    n_period_cols: int,
) -> None:
    end_col = 2 + n_period_cols
    reqs: list[dict] = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": end_col,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": HEADER_BG,
                        "textFormat": {"bold": True, "foregroundColor": HEADER_FG},
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": n_data_rows,
                    "startColumnIndex": 0,
                    "endColumnIndex": 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"foregroundColor": LINK_BLUE, "underline": True}
                    }
                },
                "fields": "userEnteredFormat.textFormat",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": n_data_rows,
                    "startColumnIndex": 2,
                    "endColumnIndex": end_col,
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
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": 1,
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
                    "startIndex": 1,
                    "endIndex": 2,
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
                    "startIndex": 2,
                    "endIndex": end_col,
                },
                "properties": {"pixelSize": 420},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 1,
                    "endIndex": n_data_rows,
                },
                "properties": {"pixelSize": 72},
                "fields": "pixelSize",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": tldr_row_0,
                    "endRowIndex": tldr_row_0 + 1,
                    "startColumnIndex": period_col_idx,
                    "endColumnIndex": period_col_idx + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "bold": True,
                            "fontSize": 11,
                            "foregroundColor": HEADER_FG,
                        }
                    }
                },
                "fields": "userEnteredFormat.textFormat",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": tldr_row_0 + 1,
                    "endRowIndex": tldr_row_0 + 1 + top5_n,
                    "startColumnIndex": period_col_idx,
                    "endColumnIndex": period_col_idx + 1,
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
                    "startIndex": tldr_row_0 + 1,
                    "endIndex": tldr_row_0 + 1 + top5_n,
                },
                "properties": {"pixelSize": 40},
                "fields": "pixelSize",
            }
        },
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]
    sheets_api(access, spreadsheet_id, "POST", ":batchUpdate", body={"requests": reqs})


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("draft", help="Read Sheet1 status columns → draft JSON")
    d.add_argument("--out", required=True, help="Output draft JSON path")
    d.add_argument("--spreadsheet-id", help="Override spreadsheet ID")
    d.set_defaults(func=cmd_draft)

    a = sub.add_parser("apply", help="Insert period column on Changes tab only")
    a.add_argument("--draft", required=True, help="Filled draft JSON path")
    a.add_argument("--spreadsheet-id", help="Override spreadsheet ID")
    a.add_argument("--dry-run", action="store_true")
    a.set_defaults(func=cmd_apply)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
