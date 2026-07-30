---
name: jira-plan-inventory
description: >-
  Inventory which Jira issues appear in a Jira Plan (Advanced Roadmaps) timeline
  view, filtered by the user's own project, labels, and/or components. Use when
  asked what is in a plan URL, which issues match a label/component in a plan
  view, plan inventory, or "what's on this roadmap for my team."
---

# Jira Plan inventory (by project / label / component)

Given a **Jira Plan timeline URL**, list the issues that are actually in that plan
(and optional saved view), then filter them by **the user's search criteria**
(project, label, component). Works with **each person's own Jira login**.

This is the workflow for questions like:

- “Look at this plan view and tell me which of *my* items are in the list”
- “Same plan inventory, but for OCP Networking labels/components”
- “Which Outcomes/Features in this roadmap map to my component?”

## Important concepts (read before answering)

1. **Plan issue sources ≠ visible list.** A plan loads issues from filters/boards/projects. A **saved view** (`vid=`) may further restrict hierarchy levels, projects, components, etc.
2. **Project key ≠ what the UI looks like.** Features may be `OCPSTRAT-*` / `VIRTSTRAT-*` while parent **Outcomes** are often `HPSTRAT-*`. If the user says they “see more Outcomes,” include **parent Outcomes** of matches (`--include-parents`), not only same-project Outcomes.
3. **Public Plans admin API is not enough.** `GET /rest/api/3/plans/plan/{id}` often returns 403 (needs Administer Jira). Use the **JPO** endpoints below (same as the UI).
4. **Always use the coworker's credentials** (their `.env_jira`), never someone else's token.

## Prerequisites (coworker setup — once)

1. Access to this skill folder (clone `JIRA_MCP_TOOLS` or copy `.cursor/skills/jira-plan-inventory/`).
2. Python venv with `requests`:
   ```bash
   cd /path/to/JIRA_MCP_TOOLS
   python3 -m venv jira_mcp_env
   source jira_mcp_env/bin/activate
   pip install requests
   ```
3. **Own** API token (do not share tokens):
   ```bash
   cp .cursor/skills/jira-plan-inventory/env.jira.example .env_jira
   # Edit .env_jira with YOUR @redhat.com email and API token
   ```
   Token: https://id.atlassian.com/manage-profile/security/api-tokens  
   **Never commit** `.env_jira`.

4. Confirm access:
   ```bash
   source jira_mcp_env/bin/activate
   set -a && source .env_jira && set +a
   python3 -c "import requests,os; from requests.auth import HTTPBasicAuth; r=requests.get(os.environ['JIRA_URL'].rstrip('/')+'/rest/api/3/myself', auth=HTTPBasicAuth(os.environ.get('JIRA_USERNAME') or os.environ['JIRA_EMAIL'], os.environ['JIRA_API_TOKEN'])); print(r.status_code, r.json().get('displayName'))"
   ```

## What the agent needs from the user

Ask if missing:

| Input | Example | Required? |
|-------|---------|-----------|
| Plan timeline URL | `https://redhat.atlassian.net/jira/plans/3019/scenarios/3020/timeline?vid=2908` | Yes (or plan/scenario/view IDs) |
| Project key(s) | `OCPSTRAT`, `OBSDA` | At least one of project / label / component |
| Label(s) | `networking`, `sdn` | Optional |
| Component name(s) | `Networking`, `OVN` | Optional |
| Include parent Outcomes? | usually **yes** for roadmap views | Recommended |

Parse IDs from the URL:

- `/jira/plans/{planId}/scenarios/{scenarioId}/...`
- query `vid={viewId}` (saved view)

## Preferred: run the script

From repo root, with the coworker's `.env_jira`:

```bash
source jira_mcp_env/bin/activate
set -a && source .env_jira && set +a

python3 .cursor/skills/jira-plan-inventory/scripts/jira_plan_inventory.py \
  --url 'https://redhat.atlassian.net/jira/plans/PLAN/scenarios/SCENARIO/timeline?vid=VIEW' \
  --project OCPSTRAT \
  --component 'Networking' \
  --label some-label \
  --include-parents \
  --apply-view-hierarchy
```

Useful flags:

| Flag | Purpose |
|------|---------|
| `--project KEY` | Repeatable. Match these project keys. |
| `--label NAME` | Repeatable. OR match if issue has any listed label. |
| `--component NAME` | Repeatable. Case-insensitive component name match. |
| `--component-id ID` | Repeatable. When you already know the component id. |
| `--include-parents` | List parent issues of matches (often HPSTRAT Outcomes). |
| `--apply-view-hierarchy` | Clip to the saved view's hierarchy range. |
| `--json` | Machine-readable output. |
| `-o report.md` | Write file. |
| `--env-file PATH` | Alternate credentials file. |

### Example — OCP Networking coworker

```bash
python3 .cursor/skills/jira-plan-inventory/scripts/jira_plan_inventory.py \
  --url 'PASTE_PLAN_URL_HERE' \
  --project OCPSTRAT \
  --component Networking \
  --include-parents \
  --apply-view-hierarchy
```

Adjust `--project` / `--component` / `--label` to whatever that person uses. Multiple filters are AND across kinds (project AND label AND component) and OR within a kind (label A OR label B).

## Agent workflow

When the user pastes a plan URL and criteria:

1. Confirm **their** `.env_jira` exists (offer setup from Prerequisites). Do not use another teammate's env file.
2. Run `jira_plan_inventory.py` with their URL + criteria. Prefer `--include-parents` for strat/roadmap plans.
3. Present:
   - Plan title, view name, criteria used
   - Counts by issue type and project
   - **Parent issues** table (if any) — call out when Outcomes are a different project than Features
   - Matched issue tables grouped by type
4. If they expected more Outcomes than same-project Outcomes: explain parents, and show the parent list.
5. Offer JSON/file export if they want to share with the team.

## Manual API recipe (if the script is unavailable)

Use Basic Auth: email + API token. Base: `https://redhat.atlassian.net`.

### 1. Plan config

```http
GET /rest/jpo/1.0/plans/{planId}
```

Returns title + `issueSources` (Filter/Board/Project ids). Resolve filter JQL via:

```http
GET /rest/api/3/filter/{filterId}
```

### 2. Saved views + hierarchy metadata

```http
POST /rest/jpo/1.0/info/metadata
Content-Type: application/json

{"planId": PLAN, "scenarioId": SCENARIO}
```

Read:

- `savedViewsInfoFull.savedViews[]` — find `id == viewId` (`vid=`), note `name` and `preferences.filtersV1`
- Hierarchy range often under `HIERARCHY_RANGE_FILTER_ID` (`start`/`end` = Advanced Roadmaps level numbers)
- `hierarchy.levels` — maps issue type ids → level (e.g. Outcome vs Feature)

Common filter keys in a view:

- `PROJECT_FILTER_ID` — project id list
- `COMPONENT_FILTER_ID` — component id list
- `HIERARCHY_RANGE_FILTER_ID` — which hierarchy levels are shown

### 3. All issues currently loaded into the plan

```http
POST /rest/jpo/1.0/backlog
Content-Type: application/json

{
  "planId": PLAN,
  "scenarioId": SCENARIO,
  "filter": {
    "includeCompleted": true,
    "includeIssueLinks": true,
    "performDependencyCompletion": false
  }
}
```

Each issue has numeric `issueKey` (number only) + `jiraValues.project` (project **id**). Resolve:

```http
GET /rest/api/3/project/{projectId}
```

Build `PROJECTKEY-{issueKey}`. Also read `jiraValues.type`, `labels`, `components`, `parent`, `summary`.

### 4. Apply the coworker's criteria

Keep issues where:

- project key ∈ requested projects (if any), AND
- labels intersect requested labels (if any), AND
- components intersect requested names/ids (if any)

Optionally restrict to the view's hierarchy level range.

### 5. Parent Outcomes

For each match with `parent` set to another backlog issue id, include that parent in a separate “Parents” section — even when the parent project differs (typical for HPSTRAT Outcomes → product Features).

## Pitfalls

| Pitfall | What to do |
|---------|------------|
| `403` on `/rest/api/3/plans/plan/...` | Expected without admin; use `/rest/jpo/1.0/...` instead |
| Only 0–few same-project Outcomes | Check HPSTRAT (or other) **parents** of Features |
| Backlog count &lt; filter JQL count | Plan may omit long-closed issues (`includeCompletedIssuesFor` on the plan) |
| View filters look empty | Some keys exist without `value`; treat missing/`[]`/`{}` as “no filter” |
| Component names vs ids | Backlog returns component **ids**; resolve via `/rest/api/3/component/{id}` or match by id from the view's `COMPONENT_FILTER_ID` |
| Sharing results | Do not paste API tokens; reports with issue keys/summaries are fine for internal use |

## Sharing this skill with a coworker

1. Point them at `.cursor/skills/jira-plan-inventory/` in this repo (or send the folder).
2. They create **their own** `.env_jira` from `env.jira.example`.
3. In Cursor, they ask e.g. *“Using the jira-plan-inventory skill, what's in this plan for project OCPSTRAT component Networking?”* and paste the plan URL.

They do **not** need admin rights on Plans — only normal browse access to the plan and issues.
