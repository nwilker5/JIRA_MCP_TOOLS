# How to: copy CNV/MTV Feature Request Customer Links onto VIRTSTRAT Features

Coworker-facing runbook for the **virtstrat-customer-links** skill and the Customer Intelligence (CI) API / CLI / MCP.

This is **not** the old CIPOE Jira Account-link flow. Live customer interest uses Customer Intelligence links (`customer_mdm_pk` + `affected_by` / `interested_in`).

| Doc | Purpose |
| --- | --- |
| This HOWTO | Humans: access, install, draft → verify → create |
| [SKILL.md](./SKILL.md) | Agents: same workflow, trigger phrases, approval rules |
| SAGE guide | Platform overview: [User Guide: Accessing Customer Intelligence Data via Programmatic Tools](https://redhat.atlassian.net/wiki/spaces/CUSTINTELL/pages/467763266/User+Guide+Accessing+Customer+Intelligence+Data+via+Programatic+Tools) |
| CLI INSTALL | [rh-customers `cli/INSTALL.md`](https://gitlab.cee.redhat.com/sage/customer-intelligence/rh-customers/-/blob/main/cli/INSTALL.md) |

Skill location in this repo (pick one tree; content is mirrored):

- Public: `skills/virtstrat-customer-links/`
- Cursor: `.cursor/skills/virtstrat-customer-links/`

GitHub: https://github.com/nwilker5/JIRA_MCP_TOOLS/tree/main/skills/virtstrat-customer-links

---

## What the process does

1. Find customers already linked (CI) on **CNV or MTV Feature Requests** that are linked to a **VIRTSTRAT Feature**.
2. Find which of those customers are **missing** on the VIRTSTRAT Feature.
3. Live-check Production CI (warehouse can lag).
4. Create the missing CI links (SSO user is the linker).
5. Optionally post a Red Hat Employee Jira note (no customer names) + `ai-sdlc-assisted`.

**Default scope**

| Side | Filter |
| --- | --- |
| VIRTSTRAT | Feature (`issuetype = 10142`), any status |
| CNV | Feature Request only (`issuetype = 10111`) |
| MTV | Feature Request only (`issuetype = 10111`), **always in scope** |

---

## Access you need

Ask SAGE / Customer Intelligence if anything below fails with 403.

1. **Customer Intelligence write** (Production): create links via MCP or `rh_customers`.
2. **Dataverse**: Interested Parties + Jira marts (gap SQL), or someone shares a CSV from that SQL.
3. **Optional Jira notes**: personal Jira API token and/or VME Automation Bot env (see `env.jira.example` / `env.bot.example` under `.cursor/skills/virtstrat-customer-links/`). Never commit tokens.

Creates are attributed to **your SSO identity**, not the VME bot. The bot is only for the optional Jira comment.

---

## Path A: Agent + skill (Cursor / Codex)

### 1. Get the skill

Clone or pull [JIRA_MCP_TOOLS](https://github.com/nwilker5/JIRA_MCP_TOOLS), or copy `skills/virtstrat-customer-links/` (and ideally `.cursor/skills/virtstrat-customer-links/` for scripts + SQL) into your workspace.

### 2. Wire MCP

In Cursor `mcp.json`, Production CI MCP:

```json
{
  "mcpServers": {
    "customer-intelligence": {
      "url": "https://rh-customers-mcp.apps.ext.spoke.prod.us-east-1.aws.paas.redhat.com/mcp"
    }
  }
}
```

Also enable **Dataverse** MCP if you will run the gap SQL yourself (`user-dataverse-agent-mcp`).

On auth errors: authenticate the CI MCP once (`mcp_auth` for namespace `user-customer-intelligence`), then retry.

Repo `.cursor/permissions.json` allowlists CI tools so batch creates are less likely to double-prompt. Approvals mode should be Auto-review or Allowlist. If Run Mode is locked by admin, use **Path B (CLI)** for creates.

### 3. Prompt the agent

Examples:

- “Draft missing customer links from CNV/MTV Feature Requests onto VIRTSTRAT Features”
- “Live-verify the customer links draft, then create the batch”
- “Post Red Hat Employee customer-links notes on the updated Features”

The agent should follow [SKILL.md](./SKILL.md): one human gate for the whole draft, then create without per-link re-asks.

### 4. Prefer CLI if MCP writes hang

MCP `create_link` timeouts are often Cursor approval UX, not API denial. Install `rh_customers` (Path B) and ask the agent to emit + run the CLI create script after you approve the draft once.

---

## Path B: CLI + scripts (recommended for reliable creates)

CLI and MCP talk to the **same** Production API. A link created with the CLI shows up immediately in MCP `search_links` / `get_issue_links`.

### 1. Install `rh_customers`

Official steps: [INSTALL.md](https://gitlab.cee.redhat.com/sage/customer-intelligence/rh-customers/-/blob/main/cli/INSTALL.md).

Notes from practice:

- INSTALL may still pin `VERSION=v0.7.0`. Registry tags go through **v1.1.0+**; prefer the newest tag you can pull (`images.paas.redhat.com/customer-intel-stage/rh-customers-cli`).
- On macOS Apple Silicon, binary path in the image is `/binaries/rh_customers-darwin-arm64`.
- If Podman overlay is broken, `skopeo copy … oci:…` then extract the layer works.
- Put the binary on `PATH` as `~/.local/bin/rh_customers`.
- There is **no** working `rh_customers --version` / `version` command on current builds. Use:

```bash
export PATH="$HOME/.local/bin:$PATH"
rh_customers auth login
rh_customers status
rh_customers whoami
rh_customers create link --help
```

Create flag is **`--customer-mdm`**, not `--customer-mdm-pk`.

### 2. Discover gaps (Dataverse)

Run the SQL in `.cursor/skills/virtstrat-customer-links/sql/virtstrat_cnv_customer_gaps.sql` (CNV **and** MTV FRs by default). Export CSV.

Draft only (never creates links):

```bash
cd /path/to/JIRA_MCP_TOOLS
python3 .cursor/skills/virtstrat-customer-links/scripts/copy_customer_links_to_virtstrat.py \
  --from-csv path/to/gaps.csv \
  --write-draft
```

Produces `virtstrat_customer_links_draft.json` (one row per `(VIRTSTRAT, customer_mdm_pk)`).

### 3. Live-verify before create

Warehouse can lag. Drop pairs that already exist in Production.

**MCP (bulk):** `search_links` with `type=issue_key`, `q=VIRTSTRAT-`, page `limit=100`.

**CLI (per Feature or scripted):**

```bash
rh_customers search links -t issue_key -q VIRTSTRAT-249 --limit 100
```

Response shape uses `response.results` (not `items`). Filter the draft against live `(issue_key, customer_mdm_pk)` pairs. Helper: `scripts/verify_draft_against_search_links.py` if you paste a search dump.

### 4. Human gate once

Review the draft table. Approve the **whole** batch once. Do not approve link-by-link.

### 5. Create

```bash
rh_customers auth login   # SSO; tokens expire (~5 min): re-login if creates start failing

python3 .cursor/skills/virtstrat-customer-links/scripts/emit_create_link_commands.py \
  --draft virtstrat_customer_links_draft.json \
  --format rh-customers > /tmp/ci_create_links.sh

# Optional: remove interactive auth line if you already logged in
# Then run:
bash /tmp/ci_create_links.sh
```

Or create one link:

```bash
rh_customers create link \
  --issue-key VIRTSTRAT-249 \
  --customer-mdm 120118 \
  --context affected_by
```

Success looks like `"Customer link created"` / `"status": "success"`. Re-create of the same triple returns `"Link already exists for this issue, customer, and context"`.

### 6. Confirm

Re-search a few Features (or bulk `VIRTSTRAT-`). Spot-check in Jira Customer Links / Interested Parties UI.

### 7. Optional Jira notes

```bash
source jira_mcp_env/bin/activate   # if using this repo’s venv
python3 .cursor/skills/virtstrat-customer-links/scripts/post_customer_link_jira_note.py \
  --issue VIRTSTRAT-249 \
  --issue VIRTSTRAT-529 \
  --replace-personal-comment
```

Posts Red Hat Employee-only: `Customer links were updated.` plus AI attribution; ensures `ai-sdlc-assisted`; unwatches bot (and personal watcher when rules allow). **Do not** put customer names in that comment.

Log the batch on the Q4 DEVO hygiene story if your team uses one (example: DEVO-288).

---

## MCP vs CLI cheat sheet

| Goal | Tool |
| --- | --- |
| Gap discovery at scale | Dataverse SQL (skill SQL file) |
| Live read / verify | MCP `search_links` / `get_issue_links`, or `rh_customers search` / `get` |
| Reliable batch create | `rh_customers create link` (preferred if MCP approvals flake) |
| Agent-native create | MCP `create_link` from the **parent** chat, allowlisted, batches of ≤5–10 |
| Jira attribution comment | `post_customer_link_jira_note.py` (VME bot) |

Production API base (CLI default):  
`https://rh-customers-api.apps.ext.spoke.prod.us-east-1.aws.paas.redhat.com`  

API `/health` may report its own version (for example `0.1.0`). That is **not** the CLI image tag.

---

## Agent-only checklist (short)

1. CI MCP (+ Dataverse) authenticated.
2. Run FR-scoped SQL (CNV+MTV) or load CSV → draft JSON.
3. Bulk live-verify; drop already-live pairs.
4. Show draft; **ask once** to create.
5. Create all remaining (CLI script or MCP batches).
6. Re-verify; report created / failed / still missing.
7. If asked: Jira notes + label; keep watcher on DEVO issues.

---

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| 403 on create | Missing CI power-user/admin group; ask SAGE |
| MCP `create_link` hangs / double Approve | Use CLI path; check Cursor allowlist / Auto-review |
| `auth: none` / token expired | `rh_customers auth login` again |
| `unknown flag: --version` | Expected; use `status` / `whoami` |
| `--customer-mdm-pk` rejected | Use `--customer-mdm` |
| Draft still shows gaps after create | Warehouse lag; trust live `search` / UI |
| Podman cannot extract image | Use `skopeo copy` + tar extract of the OCI layer |
| GitLab INSTALL.md needs login | Use Red Hat SAML on gitlab.cee; or pull the OCI image from the registry directly |

---

## Related

- Skill triggers and agent rules: [SKILL.md](./SKILL.md)
- Gap SQL: `.cursor/skills/virtstrat-customer-links/sql/virtstrat_cnv_customer_gaps.sql`
- Emit creates: `scripts/emit_create_link_commands.py`
- CIPOE Account-link copy is a **different** skill (`virtstrat-cipoe-links`). Do not mix the two.
