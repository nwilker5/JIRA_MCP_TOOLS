---
name: virt-migration-risks-changes
description: >-
  Compare the two newest Status date columns on Virt Migration Betterment: Risks
  (Sheet1) and insert a biweekly delta column on the Changes tab only — Topic and
  Assignee stay left; new period goes in column C and older change columns shift
  right. TLDR Top 5 sits under that period's column. Use for "risks changes",
  "migration risks biweekly", "compare status columns", or "add changes column".
---

# Virt Migration Risks — biweekly Changes tab

Two-phase workflow for spreadsheet
[Virt Migration Betterment: Risks](https://docs.google.com/spreadsheets/d/1pVYpmz4LMInpme4YPUexM1PaAiTBj376bcLTsMwj2MA/edit):

1. **Draft** — read Sheet1's two newest `Status Month Day, Year` columns (read-only)
2. **Apply** — write **only** the `Changes` tab: insert a new period column at **C**, shift older period columns right, put **TLDR — Top 5** under that column

**Never** edit Sheet1 (or Duplicate). Source status text stays on Sheet1; the Changes tab is the running history of 2-week deltas.

## Credentials

| System | Whose login | How |
|--------|-------------|-----|
| Google | **The person running the skill** | `gws auth login -s sheets,drive` |

Uses direct OAuth token refresh (same pattern as VBWindows sheet) to avoid gws quota-project 403s.

## Layout (Changes tab only)

| Col | Content |
|-----|---------|
| A | Topic — hyperlink to matching Sheet1 row |
| B | Assignee |
| C | **Newest** period — `Changes Mon D–Mon D, YYYY` (per-row delta) |
| D+ | Prior period columns (shifted right each run) |

Below the data rows, **in that period's column only**:

- `TLDR — Top 5`
- five `• …` bullets

## Commands

From repo root (venv activated):

```bash
# Draft JSON from Sheet1 status columns (read-only)
python3 .cursor/skills/virt-migration-risks-changes/scripts/virt_migration_risks_changes.py draft \
  --out risks_changes_draft.json

# After agent fills change + top_5_changes on every row:
python3 .cursor/skills/virt-migration-risks-changes/scripts/virt_migration_risks_changes.py apply \
  --draft risks_changes_draft.json

# Preview apply
python3 .cursor/skills/virt-migration-risks-changes/scripts/virt_migration_risks_changes.py apply \
  --draft risks_changes_draft.json --dry-run
```

Override spreadsheet: `--spreadsheet-id` or `RISKS_SHEET_ID` in the environment.

## Agent workflow (required)

1. Run **draft**. Confirm the two Status column titles and the window dates.
2. For each item with a text change, write `change` (1–3 sentences: what moved vs the prior period). Skip or leave empty only when status text is unchanged (script already filters identical text).
3. Fill `top_5_changes` with exactly **5** bullets — most consequential movements. One sentence each.
4. Show a short draft (table + Top 5) to the user.
5. On approval, run **apply** (creates `Changes` tab if missing; otherwise inserts at column C).
6. Return the Changes tab URL from script stdout.

## Rules

- **Changes tab only** — never insert columns or write cells on Sheet1
- **Insert at C** — each apply adds the newest period at C and shifts older change columns right (running biweekly history)
- **Top 5 under the new column** — not a merged block across the sheet; not on Sheet1
- Topic links always point at the corresponding Sheet1 row (`#gid=…&range=A{n}`)
- Do not commit draft JSON if it contains sensitive customer detail beyond what is already in the sheet

## Trigger phrases

- risks changes / migration risks biweekly
- compare status columns / status july vs …
- add changes column / update the Changes tab
- TLDR top 5 for risks sheet

## Troubleshooting

| Problem | Fix |
|---------|-----|
| gws / Sheets 403 quota project | Script refreshes OAuth directly; re-run `gws auth login -s sheets,drive` |
| Fewer than 2 `Status …` date columns on Sheet1 | Add a new Status date column on Sheet1 first (manual); skill only reads them |
| Empty `change` on apply | Agent must fill draft JSON before apply |
| Wrong spreadsheet | Pass `--spreadsheet-id` or set `RISKS_SHEET_ID` |
