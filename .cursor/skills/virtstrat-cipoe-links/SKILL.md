---
name: virtstrat-cipoe-links
description: >-
  Copy missing CIPOE (customer escalation) Account links from linked CNV and/or
  MTV issues onto VIRTSTRAT Features. Dry-run by default; execute as VME
  Automation Bot or personal account; removes executor as watcher after updates.
  Use for "cipoe links", "draft cipoe", "missing cipoe", "cnv mtv cipoe",
  "copy cipoe to virtstrat", or "run cipoe process".
---

# CNV/MTV → VIRTSTRAT CIPOE link copy

Finds **VIRTSTRAT Features** linked to **CNV** and/or **MTV** issues that already have **CIPOE** Account links, then copies any missing CIPOE links onto the VIRTSTRAT Feature.

| Step | What happens |
|------|----------------|
| 1 | Fetch VIRTSTRAT Features + issuelinks |
| 2 | Map VIRTSTRAT → CNV and/or MTV links; note existing CIPOE on VIRTSTRAT |
| 3 | Check each linked CNV/MTV for CIPOE links |
| 4 | Create missing Account links on VIRTSTRAT; comment; unwatch executor |

**Default source is both** (`--source both`). Use `--source cnv` or `--source mtv` to limit.

**Default is dry-run** (no Jira writes). Use `--execute` to apply.

## Prerequisites

```bash
# Personal (dry-run / optional execute)
cp .cursor/skills/virtstrat-cipoe-links/env.jira.example .env_jira
# Edit: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN

# VME Automation Bot (preferred for --execute)
cp .cursor/skills/virtstrat-cipoe-links/env.bot.example .env_vme_automation_bot
# Edit: JIRA_API_TOKEN for vme-automation-bot@redhat.com

source jira_mcp_env/bin/activate
pip install jira
```

**Credentials are never stored in the skill.** Only placeholder examples are committed. Each person copies an example to their own local env file (gitignored). Never commit `.env_jira` or `.env_vme_automation_bot`.

## Run

**Preferred (repo root):**

```bash
# Draft both CNV + MTV (default)
./run_copy_cipoe_links_to_virtstrat.sh

# CNV only / MTV only
./run_copy_cipoe_links_to_virtstrat.sh --source cnv
./run_copy_cipoe_links_to_virtstrat.sh --source mtv

# Execute as VME Automation Bot (recommended)
./run_copy_cipoe_links_to_virtstrat.sh --execute --bot

# Execute as personal account (ask first — adds you as watcher)
./run_copy_cipoe_links_to_virtstrat.sh --execute

# Exclude specific CIPOE keys
./run_copy_cipoe_links_to_virtstrat.sh --exclude CIPOE-30227
```

Log file (appended): `cipoe_link_copy.log` in the repo root.

## Agent workflow

1. **Dry-run first** unless the user explicitly skips preview.
2. Default to **`--source both`** unless the user asks for CNV-only or MTV-only.
3. Present the preview table (VIRTSTRAT, CIPOE, Source CNV/MTV, Customer, Action).
4. **Before `--execute`**, ask which account:
   - **VME Automation Bot** (`--bot`) — preferred
   - **Personal account** — only if the user explicitly chooses it
5. On execute: post **Red Hat Employee** comments and **remove the executor as watcher**.

Also follow:
- `.cursor/rules/jira-batch-no-watcher.mdc`
- `.cursor/rules/jira-claude-attribution.mdc`

## Link direction (IMPORTANT)

```python
jira.create_issue_link(
    type="Account",
    inwardIssue=virtstrat_key,  # VIRTSTRAT shows "impacts account"
    outwardIssue=cipoe_key,     # CIPOE shows "account is impacted by"
)
```

## Comments

Visibility: **Red Hat Employee** only.

```text
Missing CIPOE links were added from linked CNV items. N link(s) added.
# or "... linked MTV items ..." / "... linked CNV/MTV items ..."

---
*This comment was added via Claude AI assistant.*
```

Link-limited CIPOE (e.g. `CIPOE-30227`) adds a review notice. Tracked in `LINK_LIMITED_CIPOE`.

## Trigger phrases

- draft cipoe / preview cipoe / cipoe dry-run
- copy cipoe links / missing cipoe / cnv mtv cipoe
- run cipoe process / execute cipoe / run as vme bot

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot token missing | Create `.env_vme_automation_bot` from `env.bot.example` |
| Personal 401 | Check `.env_jira` username matches token owner |
| `ModuleNotFoundError: jira` | `pip install jira` in `jira_mcp_env` |
| LINK LIMIT on CIPOE | Expected for known capped items |
| Comment skipped | Review/automation comment already present |
