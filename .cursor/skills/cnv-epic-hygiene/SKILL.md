---
name: cnv-epic-hygiene
description: >-
  Report open CNV epics that violate Development Process rules: missing components
  and/or missing VIRTSTRAT Feature parent. Use for "cnv epic hygiene", "epics without
  components", "orphan epics", "no feature parent", "development process epics",
  or CNV planning hygiene checks.
---

# CNV epic hygiene (Development Process)

Finds **open CNV epics** that do not meet the [CNV Development Process](https://redhat.atlassian.net/wiki/spaces/cnv/pages/268599631/Development+Process):

| Rule | What we check |
|------|----------------|
| **Epic components** | Each epic should have at least one Jira **component** |
| **Parent Feature** | Each epic should have a **parent link** to a **Feature** in VIRTSTRAT (not an orphan, Initiative, or Feature Request) |
| **Not closed** | `status != Closed` |

Parent issuetype cannot be filtered reliably in JQL alone; the script resolves each parent via the API.

## Prerequisites (each user uses their own login)

1. **Clone** this repo (skill lives under `.cursor/skills/cnv-epic-hygiene/`).
2. **Python venv** (from repo root):
   ```bash
   python3 -m venv jira_mcp_env
   source jira_mcp_env/bin/activate
   pip install -r requirements.txt
   ```
3. **Credentials** — one-time setup (not tied to any named user file):
   ```bash
   cp .cursor/skills/cnv-epic-hygiene/env.jira.example .env_jira
   # Edit .env_jira: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
   ```
   - Token: https://id.atlassian.com/manage-profile/security/api-tokens
   - **Never commit** `.env_jira`.

4. **Test access:**
   ```bash
   source load_jira_env.sh
   python3 test_jira_connection.py
   ```

## Run the report

**Preferred (repo root):**

```bash
./run_cnv_epic_hygiene.sh
```

**Exclude known exceptions** (template + release checklist epics):

```bash
./run_cnv_epic_hygiene.sh --exclude-template --exclude-release-checklist
```

**JSON** (for automation):

```bash
python3 .cursor/skills/cnv-epic-hygiene/scripts/cnv_epic_hygiene.py --json
```

**Custom env file:**

```bash
python3 .cursor/skills/cnv-epic-hygiene/scripts/cnv_epic_hygiene.py --env-file /path/to/my.env
```

## Agent workflow

When the user asks for CNV epic hygiene, orphan epics, epics without components, or Development Process epic checks:

1. Confirm `.env_jira` exists (or offer setup from **Prerequisites**).
2. Run the script from the **repo root** — use `.env_jira`, **not** `.env_wilker_jira` or other personal env files unless the user explicitly points to them.
3. Present the markdown report (two tables):
   - **No component and no Feature parent** — primary violations
   - **No component — Feature parent OK** — still need a component assigned
4. Call out epics with **wrong parent type** (Initiative, Feature Request, etc.) when present.
5. Include the **bulk Jira URL** from the report when the primary list is non-empty.
6. If the user wants a cleaner list, re-run with `--exclude-template --exclude-release-checklist`.

**Do not** embed or commit API tokens. **Prefer the script** over ad-hoc MCP queries so results are consistent and paginated. MCP is optional if the user has Atlassian MCP and no local `.env_jira`.

## JQL reference

| Query | JQL |
|-------|-----|
| Open epics, no components | `project = CNV AND issuetype = Epic AND status != Closed AND component is EMPTY` |

Feature parent check: `parent.fields.issuetype.name == "Feature"` (typically VIRTSTRAT keys).

## Output format

**Summary line:**

```text
Open epics with no component: N | No component and no Feature parent: X | No component but has Feature parent: Y
```

**Primary table columns:** Key, Status, Assignee, Fix version, Parent, Parent type, Summary

**Secondary table:** epics that only need a component (Feature parent already set).

## Known exceptions

| Item | Notes |
|------|--------|
| `CNV-4600` | Epic template — omit with `--exclude-template` |
| `CNV-Release-Checklist` label | Release checklist epics — omit with `--exclude-release-checklist` |
| Initiative parent | e.g. HPSTRAT — doc says replace with Feature parent |
| Feature Request parent | Not a VIRTSTRAT Feature; counts as violation |

## Sharing with the team

1. Commit/pull this repo so `.cursor/skills/cnv-epic-hygiene/` is available.
2. Each person creates their own `.env_jira` (never shared).
3. In Cursor, ask: *"Run CNV epic hygiene"* or *"Which open epics have no components and no feature parent?"*

Without the full repo: copy `cnv-epic-hygiene/` to `~/.cursor/skills/`, install `requests`, and use `--env-file` pointing at your credentials file.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| 401 Unauthorized | Regenerate API token; check `JIRA_USERNAME` matches token owner |
| Empty results | Confirm Jira access to project CNV |
| `ModuleNotFoundError: requests` | `pip install requests` in active venv |
| Script not found | Run from repo root or pass full path to `cnv_epic_hygiene.py` |
