# JIRA MCP Tools

Simple command-line tools for managing JIRA filters and boards.

📱 **Mac users**: See [README_MAC.md](README_MAC.md) for detailed macOS setup instructions with Homebrew.

## Quick Start

### 1. Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### 2. Setup Environment Variables

Copy the example environment file and customize it with your JIRA credentials:

```bash
cp setup_jira_env.sh.example setup_jira_env.sh
```

Edit `setup_jira_env.sh` and add your JIRA credentials:
- `JIRA_URL` - Your JIRA instance URL (e.g., `https://issues.redhat.com`)
- `JIRA_USERNAME` - Your JIRA username or email
- `JIRA_API_TOKEN` - Your JIRA Personal Access Token

Then source the environment file:
```bash
source setup_jira_env.sh
```

### 3. Test Your Authentication

Verify your JIRA connection works:

```bash
python3 test_redhat_jira.py
```

This will test different authentication methods and confirm your credentials are working.

### 4. Use the Tools

#### Delete JIRA Filters
List and delete your JIRA filters using range selection:

```bash
python3 simple_delete_jira_filters.py
```

#### Delete JIRA Boards  
List and delete JIRA boards with optional filtering:

```bash
# List all accessible boards
python3 simple_delete_jira_project_board.py

# Filter boards by name
python3 simple_delete_jira_project_board.py --filter "myproject"

# Or use environment variable
export JIRA_BOARD_FILTER="dev-team"
python3 simple_delete_jira_project_board.py
```

## Range Selection Examples

Both tools support flexible range selection:
- Single item: `3`
- Range: `1-5` (items 1 through 5)
- Multiple: `2,4,7` (items 2, 4, and 7)
- Combined: `1-3,6-8,10` (items 1-3, 6-8, and 10)

## Requirements

- Python 3.x
- Install dependencies: `pip install -r requirements.txt`
- JIRA Personal Access Token (get from your JIRA profile settings)

## Notes

- Scripts auto-detect Red Hat JIRA vs standard JIRA authentication
- All operations require confirmation before deletion
- Only delete items you own or have permission to delete

## Team Cursor / Agent skills

Project skills live under [`.cursor/skills/`](.cursor/skills/) (Cursor) and are mirrored for some workflows under [`.agents/skills/`](.agents/skills/).

**Customer Intelligence (CNV Feature Request → VIRTSTRAT):**

- Browse (no hidden folders): [`skills/virtstrat-customer-links/`](skills/virtstrat-customer-links/)
- Cursor path: [`.cursor/skills/virtstrat-customer-links/SKILL.md`](.cursor/skills/virtstrat-customer-links/SKILL.md)
- Direct GitHub: https://github.com/nwilker5/JIRA_MCP_TOOLS/tree/main/skills/virtstrat-customer-links
- Ask the agent: “draft customer links from CNV Feature Requests to VirtStrat” or “create customer intelligence links”

This repo is **public** on GitHub. Anyone can view and clone without collaborator access. Clone `main` and open the folder above if a coworker cannot see `.cursor` in the GitHub UI (dotfolders are easy to miss).

