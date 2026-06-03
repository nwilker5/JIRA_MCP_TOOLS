#!/bin/bash
# Load personal Jira credentials from .env_jira (generic — any team member).
# Usage: source load_jira_env.sh

if [ ! -f ".env_jira" ]; then
    echo "❌ .env_jira not found."
    echo "   cp .cursor/skills/cnv-epic-hygiene/env.jira.example .env_jira"
    echo "   Edit .env_jira with your JIRA_URL, JIRA_USERNAME, and JIRA_API_TOKEN."
    return 1 2>/dev/null || exit 1
fi

set -a
# shellcheck source=/dev/null
source .env_jira
set +a

if [ -d "jira_mcp_env" ]; then
    source jira_mcp_env/bin/activate
fi

if [[ -z "$JIRA_URL" || -z "$JIRA_API_TOKEN" ]]; then
    echo "❌ JIRA_URL and JIRA_API_TOKEN are required in .env_jira"
    return 1 2>/dev/null || exit 1
fi

if [[ -z "$JIRA_USERNAME" && -z "$JIRA_EMAIL" ]]; then
    echo "❌ Set JIRA_USERNAME or JIRA_EMAIL in .env_jira"
    return 1 2>/dev/null || exit 1
fi

echo "✅ Jira env loaded (${JIRA_USERNAME:-$JIRA_EMAIL} @ ${JIRA_URL})"
