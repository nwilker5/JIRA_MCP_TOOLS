---
name: virtshortlist-report
description: >-
  Report on VIRTSTRAT/HPSTRAT Features and Outcomes labeled virtshortlist (VirtShortList),
  showing Architect, assignee, status, and which items were not updated this calendar week.
  Offers draft follow-up emails to the architect (or assignee when architect is unset).
  Use for "virtshortlist", "virt short list", "shortlist report", "virtshortlist not updated",
  "email architects", or weekly shortlist hygiene checks.
---

# VirtShortList report

Lists **Feature** and **Outcome** issues with label `virtshortlist` (Jira stores it as `VirtShortList`), including the **Architect** field (`customfield_10467`), and splits them by **updated this week** vs **not** using Jira `startOfWeek()`.

## Prerequisites (each user uses their own login)

1. **Clone** this repo (or copy this skill folder into `~/.cursor/skills/virtshortlist-report/`).
2. **Python venv** (from repo root):
   ```bash
   python3 -m venv jira_mcp_env
   source jira_mcp_env/bin/activate
   pip install -r requirements.txt
   ```
3. **Credentials** — one-time setup:
   ```bash
   cp .cursor/skills/virtshortlist-report/env.jira.example .env_jira
   # Edit .env_jira: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
   ```
   - Token: https://id.atlassian.com/manage-profile/security/api-tokens
   - **Never commit** `.env_jira`.

4. **Test access:**
   ```bash
   source load_jira_env.sh
   python3 test_jira_connection.py
   ```
   (`test_jira_connection.py` may expect `JIRA_EMAIL`; set that in `.env_jira` or export it equal to `JIRA_USERNAME`.)

## Run the report

**Preferred (repo root):**

```bash
./run_virtshortlist_report.sh
```

Or:

```bash
source load_jira_env.sh
python3 .cursor/skills/virtshortlist-report/scripts/virtshortlist_report.py
```

**JSON output** (for scripts):

```bash
python3 .cursor/skills/virtshortlist-report/scripts/virtshortlist_report.py --json
```

**Custom env file:**

```bash
python3 .cursor/skills/virtshortlist-report/scripts/virtshortlist_report.py --env-file /path/to/my.env
```

**Email drafts** (stale items only):

```bash
python3 .cursor/skills/virtshortlist-report/scripts/virtshortlist_report.py --email-drafts
python3 .cursor/skills/virtshortlist-report/scripts/virtshortlist_report.py --with-email   # report + drafts
```

## Agent workflow

When the user asks for a VirtShortList report:

1. Confirm `.env_jira` exists (or offer setup steps from **Prerequisites**).
2. Run the script from the **repo root** — use your own `.env_jira`, not another teammate's credentials file.
3. Present the markdown tables from script output (or regenerate the same format from `--json`).
4. Call out:
   - Items **not updated this week** (stale)
   - Items with **Architect unset** (`—`)
   - Any change vs a prior run if the user mentions one

### Offer follow-up emails (required when stale items exist)

If **`stale_count` > 0**, after the report **always ask**:

> Would you like me to draft follow-up emails for the items not updated this week? Emails go to the **Architect** when set; otherwise to the **Assignee**.

- If the user agrees (or asks for emails directly), run:
  ```bash
  python3 .cursor/skills/virtshortlist-report/scripts/virtshortlist_report.py --email-drafts
  ```
  Or use `--with-email` to show report and drafts in one run.
- Present each draft with **To**, **Subject**, body, and the **mailto** link when an email address is available from Jira.
- Note which stale items have **no architect and no assignee** — those cannot be emailed automatically.
- Offer to adjust tone, combine/split recipients, or add the user's name/signature before sending.

**Recipient rule:** one email per person; group all their stale VirtShortList items. Prefer architect over assignee per issue.

**Do not** embed or commit API tokens. **Do not** use MCP unless the user has Atlassian MCP configured; the script works with personal API tokens only.

## JQL reference

| Query | JQL fragment |
|-------|----------------|
| All shortlist Features/Outcomes | `labels = virtshortlist AND issuetype in (Feature, Outcome)` |
| Not updated this week | `... AND updated < startOfWeek()` |
| Updated this week | `... AND updated >= startOfWeek()` |

Label matching is case-insensitive in Jira (`virtshortlist` matches `VirtShortList`).

## Output format

Present two tables:

1. **Not updated this week** — sorted by `updated` ascending (oldest first).
2. **Updated this week** — sorted by `updated` descending.

Columns: **Key** (link to `https://redhat.atlassian.net/browse/KEY`), **Type**, **Status**, **Last updated**, **Architect**, **Assignee**, **Summary**.

Summary line:

```text
Total: N | Updated this week: X | Not updated this week: Y | Missing Architect: Z
```

## Email draft format

Each draft includes:

| Field | Source |
|-------|--------|
| **To** | Architect email from Jira; if architect unset, assignee email |
| **Subject** | `VirtShortList update request — N item(s) not updated this week` |
| **Body** | Greeting, list of stale issues (key, status, last updated, summary, URL) |
| **mailto** | Link when Jira returns `emailAddress` for the recipient |

If Jira does not return an email, show the display name and ask the user to look up the address.

## Sharing with coworkers

1. Commit/pull this repo so `.cursor/skills/virtshortlist-report/` is available.
2. Each person creates their own `.env_jira` (never shared).
3. In Cursor, ask: *"Run the virtshortlist report"* or *"Which virtshortlist items weren't updated this week?"* — the agent should load this skill and run the script.

To use **without** the full repo: copy `virtshortlist-report/` to `~/.cursor/skills/`, install `requests`, and keep `env.jira.example` → `.env_jira` beside the script when running:

```bash
python3 ~/.cursor/skills/virtshortlist-report/scripts/virtshortlist_report.py --env-file ~/.env_jira
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| 401 Unauthorized | Regenerate API token; check `JIRA_USERNAME` matches token owner |
| Empty results | Confirm label `VirtShortList` on issues; check Jira project access |
| `ModuleNotFoundError: requests` | `pip install requests` in active venv |
| Script not found | Run from repo root or pass full path to `virtshortlist_report.py` |
