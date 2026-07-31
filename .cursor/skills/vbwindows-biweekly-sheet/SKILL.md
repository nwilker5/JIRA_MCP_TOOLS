---
name: vbwindows-biweekly-sheet
description: >-
  Draft VBWindows (label=VBWindows) biweekly executive briefs for a user-supplied
  2-week end date and publish them as a NEW Google Sheets tab with clickable keys
  and Color Status tokens. Uses the running user's Jira (.env_jira) and Google
  (gws) logins — never another person's credentials. Use for "vbwindows biweekly",
  "vbwindows sheet", "VBWindows executive brief spreadsheet", or "add VBWindows tab".
---

# VBWindows biweekly → Google Sheet

Two-phase workflow for issues labeled `VBWindows`:

1. **Fetch** — Jira activity for the 2-week window ending on the user-supplied date
2. **Publish** — agent fills `exec_brief`s, then script creates a **new** Sheet tab

## Credentials (critical)

| System | Whose login | How |
|--------|-------------|-----|
| Jira | **The person running the skill** | `./.env_jira` from `env.jira.example` |
| Google | **The person running the skill** | `gws auth login -s sheets,drive` |

**Never** use `.env_wilker_jira`, `.env_vme_automation_bot`, or another user's tokens for this skill. Do not fall back to those files.

Print / confirm acting Jira and Google identities before write (script prints them on stderr).

## Prerequisites

```bash
python3 -m venv jira_mcp_env && source jira_mcp_env/bin/activate
pip install requests

cp .cursor/skills/vbwindows-biweekly-sheet/env.jira.example .env_jira
# Edit .env_jira with YOUR Jira email + API token — never commit.

gws auth login -s sheets,drive   # YOUR Google account
```

Default spreadsheet: [VBWindows Executive Brief](https://docs.google.com/spreadsheets/d/12NsWug2zDvtd1_ry9cZBFM_Fgv4fM7yBZND0PudMCoU/edit)  
Override: `VBWINDOWS_SHEET_ID` in `.env_jira` or `--spreadsheet-id`.

## End date → window

Ask for **`--end-date YYYY-MM-DD`** if the user did not give one (end of the 2-week period, inclusive).

| Input | Window |
|-------|--------|
| `--end-date 2026-07-24` | `2026-07-10` → `2026-07-24` (end minus 14 days through end) |

Tab title base: `MMDDYYYY` from end date (e.g. `07242026`). **Always create a new tab**; if that name exists, script uses `07242026_2`, `_3`, …

## Commands

```bash
# Fetch (read-only Jira, personal .env_jira)
./run_vbwindows_biweekly_sheet.sh fetch --end-date 2026-07-24 \
  --out vbwindows_briefs_2026-07-24.json

# After agent fills exec_brief on every item:
./run_vbwindows_biweekly_sheet.sh publish --briefs vbwindows_briefs_2026-07-24.json

# Preview publish
./run_vbwindows_biweekly_sheet.sh publish --briefs vbwindows_briefs_2026-07-24.json --dry-run
```

## Agent workflow (required)

1. **Confirm end date** with the user if missing.
2. **Confirm credentials**: runner has their own `.env_jira` and `gws` session — not someone else's.
3. Run **fetch**.
4. For each item, write `exec_brief`: 2–3 executive sentences from `source_text` (changelog + comments + Status Summary). No color words in the brief body. Adjust `theme` if the suggestion is wrong.
5. Show a short draft summary to the user.
6. On approval, run **publish** (creates a new tab every time).
7. Return the spreadsheet tab URL from script stdout.

## Sheet columns

| Column | Content |
|--------|---------|
| Key | `HYPERLINK` to Jira (clickable) |
| Summary | Issue summary |
| Status | Workflow status |
| Color Status | Red / Yellow / Green / Unset — cell fill token |
| Assignee | Display name |
| Theme | Grouping label |
| Executive Brief | Agent prose |

Color Status comes from Jira `customfield_10712`, else `health-red` / `health-yellow` / `health-green` labels.

## Rules

- **New tab every run** — never overwrite an existing tab's data in place
- **Personal Jira + personal Google only** for this skill
- Do not post briefs back to Jira unless the user separately asks
- Do not commit `.env_jira` or briefs JSON containing secrets

## Trigger phrases

- vbwindows biweekly / vbwindows sheet
- VBWindows executive brief spreadsheet
- add VBWindows tab / publish VBWindows briefs
- biweekly VBWindows for \<date\>

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No `.env_jira` | Copy `env.jira.example` — do not use another user's env file |
| gws scope / auth errors | `gws auth login -s sheets,drive` as the runner |
| Sheets 403 quota project | Script uses direct OAuth token refresh (bypasses gws quota project) |
| Empty `exec_brief` on publish | Agent must fill JSON before publish |
| Tab name collision | Script auto-suffixes `_2`, `_3`, … |
