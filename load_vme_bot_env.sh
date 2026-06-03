#!/bin/bash
# Load VME Automation Bot's JIRA Environment Configuration
# Usage: source load_vme_bot_env.sh

echo "🤖 Loading VME Automation Bot JIRA Configuration"
echo "=================================================="

# Check if the environment file exists
if [ ! -f ".env_vme_automation_bot" ]; then
    echo "❌ Environment file .env_vme_automation_bot not found!"
    echo "Please make sure you're in the JIRA_MCP_TOOLS directory"
    return 1 2>/dev/null || exit 1
fi

# Load environment variables from the file
set -a  # automatically export all variables
source .env_vme_automation_bot
set +a  # stop automatically exporting

# Activate virtual environment if it exists
if [ -d "jira_mcp_env" ]; then
    echo "🐍 Activating virtual environment..."
    source jira_mcp_env/bin/activate
fi

# Verify the variables are set
echo ""
echo "✅ Environment loaded successfully!"
echo "   JIRA_URL: ${JIRA_URL}"
echo "   JIRA_USERNAME: ${JIRA_USERNAME}"
echo "   JIRA_API_TOKEN: ${JIRA_API_TOKEN:+[SET - hidden for security]}"

# Check if all required variables are set
if [[ -z "$JIRA_URL" || -z "$JIRA_USERNAME" || -z "$JIRA_API_TOKEN" ]]; then
    echo ""
    echo "⚠️  Some required variables are not set!"
    echo "Please edit .env_vme_automation_bot and add the bot credentials"
    echo ""
    echo "Missing variables:"
    [[ -z "$JIRA_URL" ]] && echo "   - JIRA_URL"
    [[ -z "$JIRA_USERNAME" ]] && echo "   - JIRA_USERNAME"  
    [[ -z "$JIRA_API_TOKEN" ]] && echo "   - JIRA_API_TOKEN"
    echo ""
    echo "📝 Get the API token from:"
    echo "   https://id.atlassian.com/manage-profile/security/api-tokens"
    echo "   (while logged in as the VME Automation Bot account)"
else
    echo ""
    echo "🎯 Ready to run JIRA scripts as VME Automation Bot!"
    echo ""
    echo "To switch back to your personal account:"
    echo "   source load_wilker_env.sh"
fi

echo ""
echo "=================================================="
