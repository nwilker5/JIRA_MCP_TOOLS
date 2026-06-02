# Getting Started with Cursor + Claude (JIRA MCP Tools)

This guide walks through setting up **Cursor** with **Claude** and the shared **JIRA_MCP_TOOLS** repo so you can use the same Jira automations and AI workflows the team uses.

## What you get

Once set up, you can ask Claude in Cursor to do things like:

- Search and update Jira issues via the Atlassian MCP integration
- Run team reports (CNV epic hygiene, virtshortlist, ACCT→CIPOE migration, CIPOE link copy, etc.)
- Assess VIRTSTRAT features and RFE quality against team rubrics
- Clone HPIA epics, write issue synopses, and more

The repo includes **Cursor skills** (`.cursor/skills/`) and **rules** (`.cursor/rules/`) that teach the agent how to run these workflows correctly.

## Repo access

This repo lives at **https://github.com/nwilker/JIRA_MCP_TOOLS**. Ask the repo owner for **collaborator access** before cloning (it is a personal repo, not a Red Hat org repo).

---

## Part 1: Install Cursor and enable Claude

### 1. Install Cursor

1. Download from [https://cursor.com](https://cursor.com)
2. Install and sign in with your work email (or GitHub/Google, depending on your org)

### 2. Cursor subscription

Claude models require a **Cursor Pro** (or Business/Team) subscription. Check with your manager or IT if Red Hat provides a license. Without Pro, you may only have limited model access.

### 3. Select Claude as your model

1. Open **Cursor Settings** (gear icon or `Cmd + ,`)
2. Go to **Models**
3. Enable a Claude model (e.g. **Claude Sonnet** or **Claude Opus**)
4. In the chat/agent panel, pick Claude from the model dropdown before starting a conversation

**Tip:** Use **Agent** mode (not just Ask) when you want Claude to run scripts, edit files, or call Jira via MCP.

---

## Part 2: Install prerequisites (macOS)

You need **Git**, **Python 3**, and **Node.js** (for the Atlassian MCP server).

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install tools
brew install git python@3.13 node

# Verify
git --version
python3 --version
node --version   # should be v18+
npx --version
```

More detail: [README_MAC.md](README_MAC.md)

---

## Part 3: Clone the repo and set up Python

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/nwilker/JIRA_MCP_TOOLS.git
cd JIRA_MCP_TOOLS

python3 -m venv jira_mcp_env
source jira_mcp_env/bin/activate
pip install -r requirements.txt
pip install jira python-dotenv   # needed for test_jira_connection.py and some scripts
```

### 2. Create your personal Jira credentials file

**Never share or commit this file.**

```bash
cp .cursor/skills/cnv-epic-hygiene/env.jira.example .env_jira
```

Edit `.env_jira` with your Red Hat credentials:

```bash
export JIRA_URL=https://redhat.atlassian.net
export JIRA_USERNAME=you@redhat.com
export JIRA_API_TOKEN=your-api-token-here
```

**Get an API token:** [https://id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

Click **Create API token**, copy it, and paste into `.env_jira`.

### 3. Test your Jira connection

```bash
source load_jira_env.sh
python3 test_jira_connection.py
```

You should see your accessible projects listed. If you get **401 Unauthorized**, regenerate the token and confirm `JIRA_USERNAME` matches the token owner.

---

## Part 4: Connect Jira to Cursor (Atlassian MCP)

This lets Claude read/search/update Jira directly in chat without you running scripts manually.

### 1. Configure MCP in Cursor

Open (or create) your global MCP config:

**`~/.cursor/mcp.json`**

Add the Atlassian server:

```json
{
  "mcpServers": {
    "mcp-atlassian": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote@latest",
        "https://mcp.atlassian.com/v1/mcp/authv2"
      ]
    }
  }
}
```

### 2. Restart Cursor and authenticate

1. **Quit and reopen Cursor** (MCP config loads on startup)
2. Go to **Settings → MCP**
3. Confirm **mcp-atlassian** shows as connected (green)
4. On first use, a browser window opens for **Atlassian OAuth** — sign in with your Red Hat account and approve access

If the server shows disconnected:

- Confirm Node.js is installed (`node --version`)
- Run manually in a terminal to see errors:
  ```bash
  npx -y mcp-remote@latest https://mcp.atlassian.com/v1/mcp/authv2
  ```
- In Cursor: `Cmd + Shift + P` → **Reload Window**

Official docs: [Atlassian Rovo MCP – IDE setup](https://support.atlassian.com/atlassian-rovo-mcp-server/docs/setting-up-ides/)

---

## Part 5: Open the project in Cursor

1. **File → Open Folder** → select your `JIRA_MCP_TOOLS` clone
2. Cursor automatically picks up `.cursor/skills/` and `.cursor/rules/` from the repo
3. Open the **Agent** panel and start chatting with Claude

---

## Part 6: Things to try

Once MCP is connected and `.env_jira` is set up, try prompts like:

| Ask Claude… | What it does |
|-------------|--------------|
| *"Run CNV epic hygiene"* | Finds open CNV epics missing components or VIRTSTRAT Feature parent |
| *"Run the virtshortlist report"* | Reports VIRTSTRAT/HPSTRAT shortlist items and stale updates |
| *"Preview CIPOE links for virtstrat"* | Dry-run copy of CIPOE links from CNV to VIRTSTRAT |
| *"Assess VIRTSTRAT-600 feature quality"* | Scores a feature against the VirtStrat playbook |
| *"Assess RFE-12345"* | RFE quality check against the VME rubric |
| *"Run the Friday ACCT report"* | Finds product issues still linked to ACCT instead of CIPOE |
| *"Get Jira issue HPIA-1234"* | Reads issue details via MCP |

For scripts that make Jira **changes** (link copy, status transitions, etc.), Claude will usually show a preview first and ask before executing.

---

## Security reminders

- **Do not commit** `.env_jira` or any file containing API tokens
- Each person uses **their own** Jira API token and OAuth login
- When Claude creates/updates Jira issues, it adds a comment noting the change was made via AI (team rule)
- Prefer **dry-run/preview** before any `--execute` command that modifies Jira

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Claude not available | Confirm Cursor Pro subscription; check **Settings → Models** |
| MCP server disconnected | Install Node 18+; restart Cursor; check `~/.cursor/mcp.json` syntax |
| OAuth fails | Confirm you can access `redhat.atlassian.net` in browser; ask admin if MCP is allowed for your org |
| Script 401 errors | Regenerate API token; verify `.env_jira` username matches token owner |
| `ModuleNotFoundError` | `source jira_mcp_env/bin/activate` then `pip install -r requirements.txt` |
| Agent can't find skills | Open the **repo root folder** in Cursor, not a subfolder |
| Can't clone repo | Ask repo owner for GitHub collaborator access |

---

## Related docs in this repo

- [README.md](README.md) — overview and ACCT→CIPOE workflow
- [README_MAC.md](README_MAC.md) — detailed macOS prerequisites
- [PRODUCTION_JIRA_SETUP.md](PRODUCTION_JIRA_SETUP.md) — Jira connection and MCP server details
- `.cursor/skills/` — per-workflow agent instructions
- `.cursor/rules/` — Jira attribution, CIPOE copy, HPIA, and other team rules
