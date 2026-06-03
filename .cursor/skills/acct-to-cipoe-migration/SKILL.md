---
name: acct-to-cipoe-migration
description: Find CNV, MTV, and VIRTSTRAT work still linked to ACCT instead of CIPOE, suggest CIPOE replacements, and optionally swap Account links. Use for the Friday ACCT report, "acct linked items", "acct instead of cipoe", "migrate acct to cipoe", or when reviewing customer account links on product issues.
---

# ACCT → CIPOE migration (CNV / MTV / VIRTSTRAT)

Customer account links on product work should use **CIPOE**, not legacy **ACCT** issues. ACCT and CIPOE are not linked to each other in Jira—matching is done by account/customer name (summary text).

## Prerequisites

From the repo root (`JIRA_MCP_TOOLS`):

1. Python venv: `source jira_mcp_env/bin/activate`
2. Credentials: copy `.cursor/skills/cnv-epic-hygiene/env.jira.example` to `.env_jira` with `JIRA_URL`, `JIRA_USERNAME`, `JIRA_API_TOKEN`  
   (or `source load_wilker_env.sh` after the file exists)

Test: `python3 test_jira_connection.py`

**Do not commit** `.env_*` files.

## What runs on Fridays

A local LaunchAgent (if installed) runs at **9:00 AM Friday**:

```bash
./run_acct_linked_report.sh
```

That executes `search_acct_linked_items.py --exclude-closed` and writes `acct_linked_items_YYYYMMDD_HHMMSS.csv` plus logs under `logs/acct_report.log`.

Schedule management:

```bash
./setup_acct_report_schedule.sh install   # enable Friday job (macOS LaunchAgent)
./setup_acct_report_schedule.sh status
./setup_acct_report_schedule.sh run-now   # run discovery + open HTML in browser
./setup_acct_report_schedule.sh uninstall
```

`./setup_acct_report_schedule.sh install` generates `~/Library/LaunchAgents/com.jira-mcp-tools.acct-linked-report.plist` from `launchagents/com.jira-mcp-tools.acct-linked-report.plist.template` (paths filled for the local clone). Legacy `com.nwilker.acct-linked-report` is removed on install if present. Anyone can run the report manually without scheduling.

## Workflow (recommended order)

### Step 1 — Discover product work still on ACCT

```bash
cd /path/to/JIRA_MCP_TOOLS
source jira_mcp_env/bin/activate
python3 search_acct_linked_items.py --exclude-closed
```

Options:

| Flag | Purpose |
|------|---------|
| `--exclude-closed` | Skip closed CNV/MTV/VIRTSTRAT (default in `run_acct_linked_report.sh`) |
| `--open-browser` | Save `acct_report_YYYYMMDD.html` and open it |
| `--quiet` | Minimal console output (scheduled runs) |

**Output:** `acct_linked_items_*.csv` — one row per product issue with ACCT link keys in the `ACCT Links` column.

**Interpretation:** Any row here is product work that still **impacts account** via ACCT and likely needs a CIPOE link instead.

### Step 2 — Suggest matching CIPOE (read-only)

Use the newest CSV from step 1 (or pass `--csv` explicitly):

```bash
python3 acct_csv_cipoe_grid.py --open-browser
```

This searches CIPOE by tokens derived from the linked **ACCT summary** (account name), filters by name similarity (`--min-similarity`, default 0.72), and writes:

- `acct_cipoe_name_grid_*.html` — review grid (open in browser)
- `acct_cipoe_name_grid_*.csv`

Useful flags:

| Flag | Purpose |
|------|---------|
| `--csv path/to/acct_linked_items_....csv` | Specific input file |
| `--on product` | Match using product summary instead of ACCT name |
| `--loose` | Show all JQL hits without similarity filter |
| `--min-similarity 0.78` | Stricter name match |

**Human review required** before any link changes. Wrong CIPOE = wrong customer on the feature.

Alternative broad draft (all ACCT inventory, not just Friday CSV):

```bash
python3 acct_cipoe_replacement_draft.py --max-acct 200 --csv
```

Compare ACCT vs CIPOE on known keys:

```bash
python3 get_acct_cipoe_comparison.py
```

### Step 3 — Replace Account links (dry-run first)

For a confirmed **ACCT → CIPOE** pair (one customer at a time):

```bash
python3 replace_acct_account_with_cipoe.py \
  --from-acct ACCT-XXX --to-cipoe CIPOE-YYYY

python3 replace_acct_account_with_cipoe.py \
  --from-acct ACCT-XXX --to-cipoe CIPOE-YYYY \
  --exclude-closed-products --execute
```

- **Default is dry-run** — no Jira writes without `--execute`
- Only affects **CNV**, **MTV**, **VIRTSTRAT** linked via Account link type
- On execute, adds **Red Hat Employee** visibility comments on touched issues
- Optional: `--plan-json plan.json` to save the discovered product list

### Link direction (Account type)

When creating or reasoning about links (same as `copy_cipoe_links_to_virtstrat.py`):

- **Product** (CNV/MTV/VIRTSTRAT): inward — shows "account is impacted by"
- **Account** (ACCT or CIPOE): outward — shows "impacts account" on the product side

API: `type="Account"`, `inwardIssue=<product>`, `outwardIssue=<CIPOE or ACCT>`.

## Agent behavior

When the user asks to run the Friday report or check ACCT vs CIPOE:

1. Run step 1 (and step 2 if they want the CIPOE grid).
2. Summarize counts by project (CNV / MTV / VIRTSTRAT) and highlight rows with strong CIPOE matches vs ambiguous ones.
3. **Never** run `--execute` on `replace_acct_account_with_cipoe.py` without explicit user approval and confirmed ACCT/CIPOE keys.
4. For Jira updates via MCP Atlassian tools, follow workspace Jira attribution rules (Claude AI assistant comment).

## Key scripts

| Script | Role |
|--------|------|
| `search_acct_linked_items.py` | Find CNV/MTV/VIRTSTRAT linked to ACCT |
| `acct_csv_cipoe_grid.py` | CIPOE name search grid from Friday CSV |
| `acct_cipoe_replacement_draft.py` | Full ACCT inventory → CIPOE candidates (read-only) |
| `replace_acct_account_with_cipoe.py` | Swap Account links ACCT → CIPOE |
| `get_acct_cipoe_comparison.py` | Side-by-side ACCT/CIPOE link check |
| `run_acct_linked_report.sh` | Wrapper for scheduled/manual discovery |
| `setup_acct_report_schedule.sh` | Install/manage Friday LaunchAgent |

## Sharing with the team

1. Clone repo, create venv (`python3 -m venv jira_mcp_env && pip install -r requirements.txt` if present), add personal `.env_jira`.
2. Run `./run_acct_linked_report.sh` any Friday (or ask the agent: "run the ACCT linked items report").
3. Review `acct_cipoe_name_grid_*.html` before executing replacements.
4. Optional: `./setup_acct_report_schedule.sh install` on macOS (plist is generated from the template; no hand-editing paths).

## Trigger phrases

- "Friday ACCT report" / "acct linked items report"
- "CNV MTV VIRTSTRAT linked to ACCT"
- "ACCT instead of CIPOE" / "migrate acct to cipoe"
- "acct cipoe grid" / "suggest cipoe for acct"
- "replace acct links with cipoe"
