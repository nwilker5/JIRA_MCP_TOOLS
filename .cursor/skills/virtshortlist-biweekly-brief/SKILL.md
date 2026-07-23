---
name: virtshortlist-biweekly-brief
description: >-
  Biweekly VirtShortList executive brief workflow: draft exec summaries from labeled
  Features/Outcomes, review with the user, then post Status Summary + Red Hat Employee
  biweekly comment as VME Automation Bot. Use for "virtshortlist biweekly", "exec brief",
  "biweekly report status", "post exec summary to virtshortlist", or weekly president handoff.
---

# VirtShortList biweekly executive brief

Two-phase workflow for issues labeled `virtshortlist` (VirtShortList):

1. **Draft** — fetch source status text; agent writes executive briefs; user reviews
2. **Execute** — VME Automation Bot overwrites **Status Summary** and adds **Red Hat Employee** comment

**Does not** change Color Status (`customfield_10712`).

## Prerequisites

```bash
python3 -m venv jira_mcp_env && source jira_mcp_env/bin/activate
pip install -r requirements.txt

cp .cursor/skills/virtshortlist-biweekly-brief/env.jira.example .env_jira
cp .cursor/skills/virtshortlist-biweekly-brief/env.bot.example .env_vme_automation_bot
# Edit both with credentials — never commit.
```

Test bot: `source load_vme_bot_env.sh` then verify `/rest/api/3/myself` returns `vme-automation-bot@redhat.com`.

## Commands

**Draft (read-only, personal credentials OK):**

```bash
./run_virtshortlist_biweekly_brief.sh draft
./run_virtshortlist_biweekly_brief.sh draft --out virtshortlist_briefs_2026-07-09.json
```

**Execute (VME bot, after approval):**

```bash
./run_virtshortlist_biweekly_brief.sh execute --briefs virtshortlist_briefs_2026-07-09.json
./run_virtshortlist_biweekly_brief.sh execute --briefs virtshortlist_briefs_2026-07-09.json --replace-comments
```

Preview execute without writes:

```bash
python3 .cursor/skills/virtshortlist-biweekly-brief/scripts/virtshortlist_biweekly_brief.py \
  execute --briefs virtshortlist_briefs_2026-07-09.json --dry-run
```

Log file: `virtshortlist_biweekly_brief.log`

## Agent workflow (required)

When the user asks for a biweekly VirtShortList exec brief:

### Phase 1 — Draft

1. Run draft fetch:
   ```bash
   ./run_virtshortlist_biweekly_brief.sh draft --out virtshortlist_briefs_$(date +%Y-%m-%d).json
   ```
2. Read each item's `source_text` (Status Summary, or latest human comment when field says "see latest status comment").
3. **Write `exec_brief` for every item** in the JSON file — executive prose, **no color indicator**, 2–3 sentences, suitable for president handoff. Do not copy source verbatim; reframe.
4. For new shortlist items with empty source, use: _"Added to the VirtShortList. Initial status assessment pending."_
5. Present the markdown draft table (re-run `draft` after updating JSON, or format from JSON).
6. **Wait for user approval** before execute.

### Phase 2 — Execute

Only after explicit user approval (e.g. "execute", "post as vme bot"):

```bash
./run_virtshortlist_biweekly_brief.sh execute --briefs virtshortlist_briefs_YYYY-MM-DD.json --replace-comments
```

- Uses **VME Automation Bot** (`.env_vme_automation_bot`) — not personal account
- Removes bot as watcher on each touched issue after update
- Use `--replace-comments` when re-running the same week to avoid duplicate bot comments

**Do not** run execute without user approval after showing the draft.

## What gets written

### Status Summary field (`customfield_10814`)

ADF document, format:

```text
YYYY-MM-DD: <executive brief — no color>
```

### Comment (Red Hat Employee visibility only)

```text
YYYY-MM-DD: <Color Status>: Biweekly Report status: <Workflow Status>

Executive summary: <same executive brief text>

---
Status Summary updated via Claude AI assistant.
```

Color Status in the comment comes from Jira `customfield_10712` (`Red` / `Yellow` / `Green` / `Unset`). It is **not** written into Status Summary.

## Briefs JSON schema

```json
{
  "report_date": "2026-07-09",
  "items": [
    {
      "key": "VIRTSTRAT-521",
      "workflow_status": "In Progress",
      "color_status": "Red",
      "source_text": "...",
      "exec_brief": "Regional disaster recovery via native storage replication remains blocked..."
    }
  ]
}
```

Required for execute: every item must have non-empty `exec_brief`.

## Rules

- Read `.cursor/rules/jira-claude-attribution.mdc` and `.cursor/rules/jira-batch-no-watcher.mdc`
- **Draft first** unless user explicitly skips preview
- **Execute as VME bot** unless user explicitly requests personal account
- **Never** put color (Red/Yellow/Green) in Status Summary or exec brief body
- **Never** commit `.env_vme_automation_bot` or briefs JSON with secrets

## Trigger phrases

- virtshortlist biweekly / biweekly exec brief
- post exec summary to virtshortlist
- biweekly report status virtshortlist
- president handoff virtshortlist
- run virtshortlist brief draft / execute virtshortlist brief

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot 401 | Refresh token in `.env_vme_automation_bot` while logged in as bot |
| Status Summary 400 ADF | Script sends ADF automatically — do not use plain string API calls |
| HPSTRAT-51 empty source | Script falls back to latest human comment |
| Duplicate bot comments | Re-run with `--replace-comments` |
| exec_brief missing on execute | Agent must fill JSON before execute |
