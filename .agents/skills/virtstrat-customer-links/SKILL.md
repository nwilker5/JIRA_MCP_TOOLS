---
name: virtstrat-customer-links
description: >-
  Draft and create missing Customer Intelligence (Customer Links) associations
  from linked CNV Feature Requests onto VIRTSTRAT Features. Discover gaps with
  Dataverse SQL, live-verify with bulk search_links, create via CI MCP
  create_link or rh_customers CLI. Use for "customer intelligence", "copy
  customer links to virtstrat", "draft customer links", "CNV FR customer links",
  or "Feature Request vs VirtStrat customer links".
---

# CNV Feature Request → VIRTSTRAT Customer Links

CIPOE Jira Account links are historical. Live customer interest is
**Customer Intelligence** (`customer_mdm_pk` + `affected_by` / `interested_in`).

This skill copies customers that already exist on linked **CNV Feature Requests**
onto the linked **VIRTSTRAT Features** when those customers are missing there.

**Do not** fall back to CIPOE Account issue links for this workflow.

Guide: https://redhat.atlassian.net/wiki/spaces/CUSTINTELL/pages/467763266/User+Guide+Accessing+Customer+Intelligence+Data+via+Programatic+Tools

## Default scope

| Side | Filter |
|------|--------|
| VIRTSTRAT | Feature (`issuetype = 10142`), any status |
| CNV | **Feature Request only** (`issuetype = 10111`), any status |
| MTV | Out of scope unless the user asks |

To include all CNV issue types, drop `AND cnv.issuetype = 10111` in the SQL.

## Who this is for

Any operator with:

1. **Dataverse** access to Interested Parties + Jira marts (gap discovery), and
2. **Customer Intelligence** write access (MCP `create_link` or `rh_customers create link`).

Creates are attributed to the **SSO user** who authenticates (not the VME bot).
Jira attribution comments (optional) use the VME Automation Bot.

## Prerequisites

### Customer Intelligence MCP (agent path)

Production MCP URL (Cursor `mcp.json`):

```json
{
  "mcpServers": {
    "customer-intelligence": {
      "url": "https://rh-customers-mcp.apps.ext.spoke.prod.us-east-1.aws.paas.redhat.com/mcp"
    }
  }
}
```

- On auth errors: call `mcp_auth` on namespace `user-customer-intelligence` once, then retry.
- Do not paste Cookie headers into `.env`.
- **403 on create** = missing power-user/admin group. Ask SAGE / Customer Intelligence; do not invent a workaround.
- Run `create_link` from the **parent agent chat** (not a Task/subagent). Cursor subagents often fail MCP write approval (`ComposerDecisionsService` / missing approval bubble).
- Prefer **batches of ≤5** parallel `create_link` calls so approval cards can attach. If calls time out, re-auth and retry; approve Allow / Allow always when prompted.

### Dataverse MCP (preferred discovery)

Namespace `user-dataverse-agent-mcp`. For the canonical SQL already in this skill, call `execute_sql` directly with that query (user-provided / skill SQL is allowed).

### Optional CLI (good for CI authors)

```bash
rh_customers auth login
rh_customers create link --help
```

Install: see the guide’s CLI INSTALL.md. Useful when MCP `create_link` approval UX is flaky.

### Optional Jira notes (after creates)

```bash
cp .cursor/skills/virtstrat-customer-links/env.jira.example .env_jira
# + .env_vme_automation_bot for Red Hat Employee comments
```

Never commit real tokens.

## Pipeline

| Step | Tool | Notes |
|------|------|-------|
| 1 Discover | Dataverse SQL `sql/virtstrat_cnv_customer_gaps.sql` | Warehouse anti-join; no CI token burn |
| 2 Deduplicate | `copy_customer_links_to_virtstrat.py --from-csv … --write-draft` | One create per `(VIRTSTRAT, mdm_pk)` |
| 3 Live verify | MCP **`search_links`** `q=VIRTSTRAT-` paged (limit 100) | **Bulk**. Do not call `get_issue_links` once per Feature |
| 4 Present draft | Table + `virtstrat_customer_links_draft.json` | Ask before create |
| 5 Create | MCP `create_link` **or** `rh_customers` | SSO-attributed; batches of ≤5 for MCP |
| 6 Confirm | Re-run bulk `search_links` for `VIRTSTRAT-` | Drop still-missing into a retry list |
| 7 Optional Jira | `post_customer_link_jira_note.py` as bot | No customer names in the comment |

### Live verify (bulk, required pattern)

```
search_links type=issue_key q="VIRTSTRAT-" limit=100 offset=0,100,200,... sort_by=issue_key sort_order=asc
```

Parse `(issue_key, customer_mdm_pk)` pairs. Drop draft rows already present live.
Warehouse can lag MCP (false positives are normal).

### Create (MCP)

For each remaining draft row:

```
create_link(
  issue_key=<virtstrat_key>,
  customer_mdm_pk=<customer_mdm_pk>,
  context=<affected_by|interested_in>   # from CNV source row
)
```

Copy attestations from the CNV link when present (`attestations=[...]`).

### Create (CLI fallback)

From a draft JSON, emit commands:

```bash
python3 .cursor/skills/virtstrat-customer-links/scripts/emit_create_link_commands.py \
  --draft virtstrat_customer_links_draft.json \
  --format rh-customers
# review, then:
# bash /tmp/ci_create_links.sh   # or run line-by-line after auth login
```

## SQL

Canonical query: `.cursor/skills/virtstrat-customer-links/sql/virtstrat_cnv_customer_gaps.sql`

Tables:

- `INTERESTEDPARTIES_DB.MARTS.FCT_CURRENT_CUSTOMER_LINKS`
- `JIRA_DB.CLOUDRHAI_MARTS.JIRA_ISSUE_NON_PII`
- `JIRA_DB.CLOUDRHAI_MARTS.JIRA_ISSUESTATUS_RHAI`
- `JIRA_DB.CLOUDRHAI_MARTS.JIRA_ISSUELINK_RHAI`

Export CSV (headers matching the SELECT), then:

```bash
./run_copy_customer_links_to_virtstrat.sh --from-csv path/to/gaps.csv --write-draft
```

The CSV script is **draft only**. It never calls `create_link`.

## Agent workflow (checklist)

1. Confirm MCP namespaces: `user-customer-intelligence`, preferably `user-dataverse-agent-mcp`.
2. Run the FR-scoped SQL (Dataverse MCP `execute_sql` or user-pasted CSV).
3. Deduplicate → draft JSON / table.
4. Bulk `search_links` for `VIRTSTRAT-`; drop already-live pairs.
5. Show verified create list. **Ask** before create.
6. Create in parent chat, ≤5 parallel `create_link` calls per batch.
7. Re-verify with bulk `search_links`. Report created / failed / still missing.
8. Optional: bot Jira note + `ai-sdlc-assisted` label; unwatch bot and personal account when keep-watcher rules allow.

```bash
source jira_mcp_env/bin/activate
python3 .cursor/skills/virtstrat-customer-links/scripts/post_customer_link_jira_note.py \
  --issue VIRTSTRAT-XXXX --replace-personal-comment
```

Comment body (Red Hat Employee only, **no customer names**):

`Customer links were updated.` plus AI attribution.

## Known caveats

- Anti-join is **per customer**, not “VIRTSTRAT has zero customers”.
- Same customer on two CNV FRs → two SQL rows; create **once** per Feature.
- `INTERESTEDPARTIES` can lag MCP; always live-verify before create.
- MCP `create_link` timeouts are often Cursor write-approval UX, not API denial. Re-auth, approve, retry; or use `rh_customers`.

## Trigger phrases

- draft customer links / preview customer intelligence virtstrat
- copy customer links from CNV / Feature Request customer links
- missing customer links on virtstrat
- CNV FR vs VirtStrat customer links
- customer intelligence API / rh-customers MCP / create customer links
