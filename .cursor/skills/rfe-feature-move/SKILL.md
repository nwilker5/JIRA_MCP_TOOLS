---
name: rfe-feature-move
description: >-
  Move RFE Feature Request issues to CNV or MTV as Feature Request via the Jira
  Cloud bulk move API. Posts a Red Hat Employee–only comment and removes the
  acting user as watcher. Each person uses their own Jira token (.env_jira).
  Use for "move RFE to CNV", "move RFE to MTV", "move feature request to CNV",
  "migrate RFE", or relocating RFE-* keys into the product projects.
---

# RFE Feature Move (RFE → CNV / MTV)

Move one or more **RFE** issues into **CNV** or **MTV** as **Feature Request**.

After each successful move the script:

1. Adds a **Red Hat Employee**–only comment (`Moved from RFE-… to CNV/MTV…` + Claude attribution)
2. Removes the **acting user as watcher** (Jira auto-watches on edit/comment)

## Prerequisites (each user uses their own login)

1. Clone this repo (skill under `.cursor/skills/rfe-feature-move/`).
2. Python venv (repo root):
   ```bash
   python3 -m venv jira_mcp_env
   source jira_mcp_env/bin/activate
   pip install requests
   ```
3. Credentials — one-time setup:
   ```bash
   cp .cursor/skills/rfe-feature-move/env.jira.example .env_jira
   # Edit .env_jira: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN
   ```
   - Token: https://id.atlassian.com/manage-profile/security/api-tokens
   - Need **Move Issues** on RFE and **Create Issues** on CNV/MTV
   - **Never commit** `.env_jira`

4. Optional: point at another env with `--env-file` (e.g. a service account). Prefer personal `.env_jira` unless the user asks for the VME bot.

## Run

From **repo root**:

```bash
source jira_mcp_env/bin/activate

# Preview
python3 .cursor/skills/rfe-feature-move/scripts/rfe_feature_move.py RFE-1234 --target CNV --dry-run

# Move to CNV
python3 .cursor/skills/rfe-feature-move/scripts/rfe_feature_move.py RFE-1234 --target CNV

# Move several to MTV
python3 .cursor/skills/rfe-feature-move/scripts/rfe_feature_move.py RFE-1 RFE-2 --target MTV

# Keep watching (skip unwatch)
python3 .cursor/skills/rfe-feature-move/scripts/rfe_feature_move.py RFE-1234 --target CNV --keep-watcher

# Custom credentials file
python3 .cursor/skills/rfe-feature-move/scripts/rfe_feature_move.py RFE-1234 --target CNV \
  --env-file .env_vme_automation_bot
```

## Agent workflow

When the user asks to move an RFE (or Feature Request) to CNV or MTV:

1. Confirm destination: **CNV** or **MTV** (ask if unclear).
2. Confirm credentials: use `.env_jira` by default. Use `.env_vme_automation_bot` only if the user asks for the VME bot / automation bot.
3. Prefer **`--dry-run` first** unless the user clearly wants immediate execute.
4. Run the script from the **repo root** with the venv activated.
5. Report a short before/after table: old key → new key, status, assignee, browse URL.
6. Confirm comment (Red Hat Employee) and watcher removal unless `--keep-watcher`.

### Do not

- Hard-code personal tokens or commit `.env_*` files
- Move to projects other than CNV/MTV with this skill
- Change issue type away from Feature Request
- Leave the acting user as watcher unless asked (`--keep-watcher`)

## API notes

| Step | Endpoint |
|------|----------|
| Move | `POST /rest/api/3/bulk/issues/move` — mapping key `{PROJECT},{issueTypeId}` |
| Poll | `GET /rest/api/3/bulk/queue/{taskId}` |
| Comment | `POST /rest/api/3/issue/{key}/comment` with `visibility: { type: group, value: "Red Hat Employee" }` |
| Unwatch | `DELETE /rest/api/3/issue/{key}/watchers?accountId=…` |

If the account cannot disable bulk notifications (`403` about bulk mail), the script retries with `sendBulkNotification: true`.

Feature Request type id is resolved live from `createmeta` for the target project (not hard-coded).

## Trigger phrases

- "move RFE to CNV"
- "move RFE to MTV"
- "move feature request to CNV"
- "migrate RFE-…"
- "RFE feature move"
