# 🚀 Production Jira MCP Setup Guide

## Overview
This guide shows you how to connect your scripts to production Jira through MCP (Model Context Protocol).

## ✅ Prerequisites Completed
- ✅ Python 3.13.7 installed
- ✅ Virtual environment created (`jira_mcp_env`)
- ✅ Required packages installed (jira, mcp, python-dotenv)

## 🔐 Step 1: Configure Jira Credentials

### Create API Token
1. Go to [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click "Create API token"
3. Give it a name (e.g., "MCP Integration")
4. Copy the generated token

### Set Environment Variables
Create a `.env` file in this directory:

```bash
# Create .env file
cat > .env << 'EOF'
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-api-token-here
EOF
```

**Replace with your actual values:**
- `JIRA_URL`: Your Jira instance URL
- `JIRA_EMAIL`: Your Jira login email
- `JIRA_API_TOKEN`: The token you just created

## 🧪 Step 2: Test Connection

Activate the virtual environment and test:

```bash
# Activate virtual environment
source jira_mcp_env/bin/activate

# Test basic Jira connection
python3 test_jira_connection.py
```

This will:
- ✅ Verify your credentials
- ✅ List accessible projects
- ✅ Test HPCIA project access
- ✅ Show sample issues

## 🚀 Step 3: Start MCP Server

Once the connection test passes:

```bash
# Start the MCP server
python3 start_mcp_jira_server.py
```

This starts an MCP server that provides Jira tools to AI assistants.

## 🔧 Step 4: Use with Your Scripts

### Option A: Direct Python Usage
With the virtual environment activated, your scripts can now use real Jira data:

```bash
# Activate environment
source jira_mcp_env/bin/activate

# Run your HPCIA search (will connect to real Jira)
python3 search_nwilker_hpcia_issues.py
```

### Option B: MCP Integration
Configure your AI assistant to use the MCP server for Jira operations.

## 🛠️ Available MCP Tools

The MCP server provides these tools:

### 1. `jira_search`
Search for issues using JQL:
```json
{
  "jql": "project = HPCIA AND (reporter = nwilker OR assignee = nwilker) AND status != Closed",
  "limit": 50,
  "fields": "key,summary,status,priority,assignee,reporter"
}
```

### 2. `jira_get_issue`
Get detailed issue information:
```json
{
  "issue_key": "HPCIA-1234",
  "fields": "*all"
}
```

### 3. `jira_get_projects`
List all accessible projects:
```json
{}
```

## 🎯 Your HPCIA Query

The exact JQL query for your needs:
```jql
project = HPCIA AND (reporter = nwilker OR assignee = nwilker) AND status != Closed
```

## 🔍 Troubleshooting

### Connection Issues
- Verify your Jira URL includes `https://`
- Check that your API token hasn't expired
- Ensure your account has access to HPCIA project

### Permission Issues
- Confirm you can access HPCIA project in the web interface
- Check if your account has "Browse Projects" permission

### Environment Issues
- Make sure virtual environment is activated
- Verify `.env` file exists and has correct values
- Check that all packages are installed

## 📁 Files Created

- `setup_production_jira_mcp.sh` - Setup script
- `test_jira_connection.py` - Connection tester
- `start_mcp_jira_server.py` - MCP server
- `search_nwilker_hpcia_issues.py` - Your HPCIA search script
- `jira_mcp_env/` - Virtual environment
- `.env` - Your credentials (create this)

## 🚀 Quick Start Commands

```bash
# 1. Set up credentials
echo "JIRA_URL=https://your-company.atlassian.net" > .env
echo "JIRA_EMAIL=your-email@company.com" >> .env
echo "JIRA_API_TOKEN=your-token" >> .env

# 2. Activate environment
source jira_mcp_env/bin/activate

# 3. Test connection
python3 test_jira_connection.py

# 4. Run your HPCIA search
python3 search_nwilker_hpcia_issues.py

# 5. Start MCP server (optional, for AI assistant integration)
python3 start_mcp_jira_server.py
```

## 🎉 Success!

Once configured, your scripts will connect to production Jira and return real data instead of simulated results!



