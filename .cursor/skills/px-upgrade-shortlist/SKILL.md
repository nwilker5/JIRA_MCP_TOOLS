---
name: px-upgrade-shortlist
description: >-
  Curate PX Impact Score–scored CNV/MTV upgrade issues into OCP upgrade, CNV
  upgrade, both, or unclear buckets with short impact summaries, ordered by
  score. Use for "px upgrade", "upgrade shortlist", "OCP vs CNV upgrade issues",
  "PX Prioritization upgrade", dashboard 10928 upgrade filter, or when someone
  asks which PX-scored issues are real upgrade problems.
---

# PX upgrade shortlist (CNV + MTV)

Builds a **curated** list of upgrade-related CNV/MTV issues from the PX Prioritization
pool. Keyword JQL alone is noisy; this skill fetches the pool, then the agent **reads
each issue** and keeps only true upgrade-context items, classified and ordered by
**PX Impact Score**.

Related dashboard: https://redhat.atlassian.net/jira/dashboards/10928  
PX user guide: https://redhat.atlassian.net/wiki/spaces/HUB/pages/190188116/PX+Prioritization+User+Guide

## Starting pool (JQL)

```jql
project in (CNV, MTV)
AND resolution = Unresolved
AND "PX Impact Score" is not EMPTY
AND text ~ "upgrade"
ORDER BY "PX Impact Score" DESC
```

Expect roughly 70–100 hits. **Do not stop at keyword matches.**

## Prerequisites (each user uses their own login)

1. **Clone** this repo (skill lives under `.cursor/skills/px-upgrade-shortlist/`).
2. **Python venv** (from repo root):
   ```bash
   python3 -m venv jira_mcp_env
   source jira_mcp_env/bin/activate
   pip install -r requirements.txt
   ```
3. **Credentials** — one-time setup:
   ```bash
   cp .cursor/skills/px-upgrade-shortlist/env.jira.example .env_jira
   # Edit .env_jira: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
   ```
   - Token: https://id.atlassian.com/manage-profile/security/api-tokens
   - **Never commit** `.env_jira`.

4. **Test access:**
   ```bash
   source load_jira_env.sh
   python3 test_jira_connection.py
   ```

## Fetch the pool (script)

**Preferred (repo root):**

```bash
./run_px_upgrade_shortlist.sh
```

**JSON** (for agent curation):

```bash
./run_px_upgrade_shortlist.sh --json
```

The script returns unresolved CNV/MTV issues with PX Impact Score that match
`text ~ upgrade`, including **rendered** numeric score, summary, description
snippet, and upgrade-related comment snippets.

## Agent workflow (required)

When the user asks for a PX upgrade shortlist / OCP vs CNV upgrade issues:

1. Confirm `.env_jira` exists (or offer setup from **Prerequisites**).
2. Run `./run_px_upgrade_shortlist.sh --json` from the **repo root**.
3. For **every** issue in the pool, read summary, description, and upgrade comments.
4. Keep an issue **only if upgrade is the real problem context** — for example:
   failure/risk during an OCP or CNV upgrade, blocks drains during upgrade,
   post-upgrade breakage, or an RFE whose primary purpose is safer/faster upgrades
   or cross-version lifecycle moves.
5. **Exclude** incidental hits, such as:
   - “customer will upgrade later when the fix lands”
   - epic checklist line “DEV Upgrade consideration”
   - storage-vendor / ODF / guest / memory “upgrade”
   - general migration bugs with no upgrade scenario
6. Classify each kept issue into exactly one bucket:
   - **OCP upgrade** — OpenShift / RHCOS / hosting-cluster upgrade
   - **CNV upgrade** — OpenShift Virtualization / operator / workload-update upgrade
   - **Both** — combined or clearly both
   - **Unclear** — upgrade involved, but OCP vs CNV not specified
7. Write a **short impact summary** (one sentence). Do **not** paste the raw Jira summary.
8. Sort the curated list by **PX Impact Score** descending (use the rendered
   numeric score from the script).
9. Present a markdown table with columns:
   - PX Impact Score
   - Upgrade type
   - Key (link to `https://redhat.atlassian.net/browse/KEY`)
   - Issue type
   - Status
   - Impact

Also report:

- size of the raw JQL pool
- how many kept vs dropped
- any borderline exclusions and why

Include Bugs and Feature Requests. Prefer actionable unresolved work; note
Verified/tracker items if you keep them.

### Output template

```markdown
| PX Impact Score | Upgrade type | Key | Issue type | Status | Impact |
|---:|---|---|---|---|---|
| 8135 | Both | [CNV-94145](https://redhat.atlassian.net/browse/CNV-94145) | Bug | POST | … |
```

Optionally also group counts by upgrade type after the table.

## Notes

- Dashboard 10928 has **no** built-in “upgrade impact” facet. Raw
  `text ~ upgrade` is noisier than this curated list.
- Getting the curated list from the dashboard alone would require labeling
  (for example `px-upgrade-impact`) or a saved filter of fixed keys.
- **PX Impact Score** is field `customfield_11003`; the readable number is in
  `renderedFields`, not the raw `rfv1:…` value.
