---
name: cnv-virtstrat-cipoe-links
description: >-
  Copy missing CIPOE (customer escalation) Account links from linked CNV issues
  onto VIRTSTRAT Features. Dry-run by default; execute as VME Automation Bot or
  personal account; removes executor as watcher after updates. Use for "cipoe
  links", "draft cipoe", "missing cipoe", "copy cipoe to virtstrat", "cnv
  virtstrat cipoe", or "run cipoe process".
---

# CNV → VIRTSTRAT CIPOE link copy

Finds **VIRTSTRAT Features** linked to **CNV** issues that already have **CIPOE** Account links, then copies any missing CIPOE links onto the VIRTSTRAT Feature.

| Step | What happens |
|------|----------------|
| 1 | Fetch VIRTSTRAT Features + issuelinks |
| 2 | Map VIRTSTRAT → CNV links; note existing CIPOE on VIRTSTRAT |
| 3 | Check each linked CNV for CIPOE links |
| 4 | Create missing Account links on VIRTSTRAT; comment; unwatch executor |

**Default is dry-run** (no Jira writes). Use `--execute` to apply.

## Prerequisites

```bash
# Personal (dry-run / optional execute)
cp .cursor/skills/cnv-virtstrat-cipoe-links/env.jira.example .env_jira
# Edit: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN

# VME Automation Bot (preferred for --execute)
cp .cursor/skills/cnv-virtstrat-cipoe-links/env.bot.example .env_vme_automation_bot
# Edit: JIRA_API_TOKEN for vme-automation-bot@redhat.com

source jira_mcp_env/bin/activate
pip install jira
```

Never commit `.env_jira` or `.env_vme_automation_bot`.

## Run

**Preferred (repo root):**

```bash
# Draft / preview
./run_copy_cipoe_links_to_virtstrat.sh

# Execute as VME Automation Bot (recommended)
./run_copy_cipoe_links_to_virtstrat.sh --execute --bot

# Execute as personal account (ask first — adds you as watcher)
./run_copy_cipoe_links_to_virtstrat.sh --execute

# Exclude specific CIPOE keys
./run_copy_cipoe_links_to_virtstrat.sh --exclude CIPOE-30227
```

**Direct:**

```bash
python3 .cursor/skills/cnv-virtstrat-cipoe-links/scripts/copy_cipoe_links_to_virtstrat.py --dry-run
```

Log file (appended): `cipoe_link_copy.log` in the repo root.

## Agent workflow

1. **Dry-run first** unless the user explicitly skips preview.
2. Present the preview table (VIRTSTRAT, CIPOE, Source CNV, Customer, Action).
3. **Before `--execute`**, ask which account:
   - **VME Automation Bot** (`--bot`) — preferred; comments/links attributed to `vme-automation-bot@redhat.com`
   - **Personal account** — only if the user explicitly chooses it
4. On execute: run with the chosen account. Script posts **Red Hat Employee** comments and **removes the executor as watcher**.
5. Report links created, link-limit failures, comments, and watcher cleanup.

Also follow:
- `.cursor/rules/jira-batch-no-watcher.mdc`
- `.cursor/rules/jira-claude-attribution.mdc`

## Link direction (IMPORTANT)

Account link type — API is counterintuitive:

```python
jira.create_issue_link(
    type="Account",
    inwardIssue=virtstrat_key,  # VIRTSTRAT shows "impacts account"
    outwardIssue=cipoe_key,     # CIPOE shows "account is impacted by"
)
```

## Comments

Visibility: **Red Hat Employee** only (no customer names in the comment body).

```text
Missing CIPOE links were added from linked CNV items. N link(s) added.

---
*This comment was added via Claude AI assistant.*
```

Link-limited CIPOE (e.g. `CIPOE-30227` / IBM at 2000-link cap) adds a review notice that not all CIPOE links could be included. Tracked in `LINK_LIMITED_CIPOE` in the script.

## Trigger phrases

- draft cipoe / preview cipoe / cipoe dry-run
- copy cipoe links to virtstrat / missing cipoe links
- cnv virtstrat cipoe / run cipoe process
- execute cipoe / run as vme bot

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot token missing | Create `.env_vme_automation_bot` from `env.bot.example` |
| Personal 401 | Check `.env_jira` username matches token owner |
| `ModuleNotFoundError: jira` | `pip install jira` in `jira_mcp_env` |
| LINK LIMIT on CIPOE | Expected for known capped items; review comment may already exist |
| Comment skipped | Review/automation comment already present on that VIRTSTRAT |
