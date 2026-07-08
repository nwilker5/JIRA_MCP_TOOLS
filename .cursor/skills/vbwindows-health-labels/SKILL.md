---
name: vbwindows-health-labels
description: >-
  Sync VBWindows issues from latest RED:/YELLOW:/GREEN: status comment using two
  tiers: perfect (Color Status + Status Summary fields) or next (health-* label +
  Status Summary). Runs as VME Automation Bot by default. Supports draft and execute.
  Use for "vbwindows health labels", "health-yellow", "color status", "status summary",
  "sync color labels", "bsod health labels", or VBWindows status comment sync.
---

# VBWindows health status sync

Aligns `VBWindows` issues with the **most recent** `RED:`, `YELLOW:`, or `GREEN:` status comment using two tiers:

## Perfect tier (preferred)

When **Color Status** and **Status Summary** are on the issue screen (e.g. VIRTCE):

| Source | Target |
|--------|--------|
| Latest `RED:` / `YELLOW:` / `GREEN:` comment | **Color Status** (`customfield_10712`) → Red / Yellow / Green |
| Comment date + text after color marker | **Status Summary** (`customfield_10814`) |

Scope: issue already has `VBWindows` label. **Do not** set `health-*` labels on perfect-tier issues.

## Next tier (fallback)

When **Color Status is not on screen** (e.g. some EPMB issues):

| Source | Target |
|--------|--------|
| Latest color comment | `health-red` / `health-yellow` / `health-green` label |
| Comment date + text after color marker | **Status Summary** (when field is on screen) |

**Status Summary** format:

```text
2026-07-08:
Backports are still in progress. Alert was changed to warn about every BSOD/panic.
```

Date = **comment timestamp**. Text = everything after `RED:`/`YELLOW:`/`GREEN:` on that comment line.

**Default is draft** (no Jira writes). Use `--execute` to apply.

**Runs as VME Automation Bot by default** (`vme-automation-bot@redhat.com` via `.env_vme_automation_bot`).

**Always read** before posting updates:
- `.cursor/rules/jira-claude-attribution.mdc`
- `.cursor/rules/jira-batch-no-watcher.mdc`

## Prerequisites

```bash
cp .cursor/skills/vbwindows-health-labels/env.bot.example .env_vme_automation_bot
# Edit: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN

source jira_mcp_env/bin/activate
pip install requests
```

## Script commands

```bash
# Draft report (VME bot)
./run_vbwindows_health_labels.sh

# Apply
./run_vbwindows_health_labels.sh --execute
```

## GitHub Actions (hourly, Monday–Friday)

Workflow: `.github/workflows/vbwindows-health-labels.yml`

Runs every hour on weekdays (UTC) as the VME bot. Also supports manual **Run workflow**.

**Repository secrets** (Settings → Secrets and variables → Actions):

| Secret | Value |
|--------|--------|
| `VME_BOT_JIRA_URL` | `https://redhat.atlassian.net` |
| `VME_BOT_JIRA_USERNAME` | `vme-automation-bot@redhat.com` |
| `VME_BOT_JIRA_API_TOKEN` | Bot API token |

Cron is UTC (`0 * * * 1-5`). Adjust in the workflow file for a different timezone or hour window.

## Agent workflow

1. **Always use VME Automation Bot** — `./run_vbwindows_health_labels.sh` (no `--personal` unless user explicitly asks).
2. **Run draft first** unless user skips preview.
3. Present report with **Perfect tier** and **Next tier** sections:
   - Perfect ok = Color Status + Status Summary match latest comment
   - Next ok = `health-*` label + Status Summary match latest comment
4. Explain which tier each issue uses (based on whether Color Status is editable).
5. On execute: `./run_vbwindows_health_labels.sh --execute`

**Do not** set `health-*` labels when the issue is on the **perfect** tier.

## Color detection

- Most recent comment with `RED:`, `YELLOW:`, or `GREEN:` at line start (case-insensitive).
- Older color comments are ignored.
- **Skip updates** when values already match the latest comment:
  - **Color Status** — not reset if already Red / Yellow / Green for that comment
  - **Status Summary** — not reset if same date and body already matches (including Jira truncation)
  - **health-* label** (next tier) — not reset if already correct

## Trigger phrases

- vbwindows health labels / sync color status
- perfect tier / next tier health sync
- status summary / color status from comment
- draft vbwindows labels / execute health label sync

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Issue on wrong tier | Check edit screen — Color Status on screen → perfect; otherwise next |
| 401 | Regenerate bot token in `.env_vme_automation_bot` |
| EPMB only gets label | Expected — Color Status not on EPMB screen (next tier) |
