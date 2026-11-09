---
name: cnv-rogue-components
description: >-
  Investigate unexpected / rogue CNV Jira components: diff the live catalog
  against the expected allowlist, and trace each suspect to its first Component
  field assignment (who, when, issue, co-set names). Use for "rogue CNV
  components", "who created this component", "unexpected CNV components",
  "Storage kubernetes-nmstate-operator", or Dan/leads hygiene emails about bad
  component names.
---

# CNV rogue component investigation

When unexpected names appear in the CNV project component catalog (or on issues),
find **who first assigned each name** via issue changelogs. That first use is
the practical origin signal (inline create / near-miss select while editing
Components). Full Jira audit (`ProjectComponentCreated`) needs Jira Admin and
is out of scope for this skill.

## What it does

| Mode | Result |
|------|--------|
| Catalog diff | Live `/project/CNV/components` vs built-in **allowlist** |
| First-use trace | Earliest Component changelog **add** per suspect name |
| Context | Actor display name + email, issue key/summary, same-edit co-set components (near-miss hint) |

**Important:** Dan’s screenshots often show **one** name like `Install, Upgrade and Operators` (missing the `CNV ` prefix), not three separate components `install` / `upgrade` / `operators`. The script matches comma-containing names as whole tokens.

## Prerequisites (each user uses their own login)

1. **Clone** this repo (skill under `.cursor/skills/cnv-rogue-components/`).
2. **Python venv** (from repo root):
   ```bash
   python3 -m venv jira_mcp_env
   source jira_mcp_env/bin/activate
   pip install -r requirements.txt
   ```
3. **Credentials** — one-time setup:
   ```bash
   cp .cursor/skills/cnv-rogue-components/env.jira.example .env_jira
   # Edit .env_jira: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
   ```
   - Token: https://id.atlassian.com/manage-profile/security/api-tokens
   - **Never commit** `.env_jira`.

4. **Test access:**
   ```bash
   source load_jira_env.sh
   python3 test_jira_connection.py
   ```

## Run

**Preferred (repo root):**

```bash
# Catalog-only: what is on CNV but not on the allowlist?
./run_cnv_rogue_components.sh --diff

# Trace named suspects (names from a screenshot / email)
./run_cnv_rogue_components.sh --suspect "Storage" "kubernetes-nmstate-operator" "Install, Upgrade and Operators"

# Diff + auto-investigate every catalog extra
./run_cnv_rogue_components.sh --diff --investigate-extras

# Wider history if first use is older than ~120 days
./run_cnv_rogue_components.sh --suspect "Storage" --since 2026-01-01 --max-scan 1000
```

**JSON** (for automation):

```bash
python3 .cursor/skills/cnv-rogue-components/scripts/cnv_rogue_components.py \
  --suspect "Storage" --json
```

**Custom env file:**

```bash
python3 .cursor/skills/cnv-rogue-components/scripts/cnv_rogue_components.py \
  --env-file /path/to/my.env --diff
```

## Agent workflow

When the user asks who created rogue CNV components, or pastes a screenshot/list of unexpected component names:

1. Confirm `.env_jira` (or user-pointed env) exists.
2. Parse the suspect list carefully:
   - Prefer exact strings from the screenshot.
   - Do **not** split `Install, Upgrade and Operators` into three names.
3. Run from **repo root** (prefer `./run_cnv_rogue_components.sh`).
4. Present the markdown report: catalog extras table + first-use table + per-component detail.
5. Call out **near-miss** patterns (rogue set in the same edit as a legitimate sibling, e.g. `Storage` with `Storage Platform` / `Storage Ecosystem`, or IUO without the `CNV ` prefix next to `CNV Install, Upgrade and Operators`).
6. Note if suspects are **already removed** from the catalog (investigation still works via changelogs in the `--since` window).
7. Offer a short reply draft for leads (who / when / issue / pattern) if the user is answering an email thread.

**Do not** print env secrets. Prefer the script over ad-hoc MCP so comma-name matching and pagination stay consistent.

## Allowlist maintenance

The expected component set lives in `scripts/cnv_rogue_components.py` as `ALLOWLIST`. When CNV **intentionally** adds a real component:

1. Update `ALLOWLIST` (and `COMMA_NAMES` if the new name contains a comma).
2. Keep zArchive handling: any name starting with `zArchive` is treated as allowed even if the exact string drifts.

## Output (what “good” looks like)

First-use table columns: Component · First use (UTC) · Who · Email · Issue · Co-set in same edit

Per suspect: catalog presence, currently assigned count, first issue summary/type/creator, near-miss hint when applicable.

## Notes

- Jira Administrator **audit** API is not required and usually 403 for normal users.
- Changelog scan of recently updated issues can take 1–3 minutes for several suspects; `--workers` defaults to 8.
- After cleanup, rogue names may be absent from the catalog and from current issues; first-use still appears from historical Component field changes.
