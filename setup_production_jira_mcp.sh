#!/bin/bash
# Production Jira MCP Setup Script
# Run this to configure your environment for MCP Jira connection

echo "🔧 Setting up Production Jira MCP Connection"
echo "============================================="

# Check if required tools are installed
echo "📋 Checking prerequisites..."

# Check Python
if command -v python3 &> /dev/null; then
    echo "✅ Python 3 found: $(python3 --version)"
else
    echo "❌ Python 3 not found. Please install Python 3.8+"
    exit 1
fi

# Check pip
if command -v pip3 &> /dev/null; then
    echo "✅ pip3 found"
else
    echo "❌ pip3 not found. Please install pip"
    exit 1
fi

echo ""
echo "🔐 Jira Configuration Required:"
echo "You need to set these environment variables:"
echo ""
echo "export JIRA_URL='https://your-company.atlassian.net'"
echo "export JIRA_EMAIL='your-email@company.com'"
echo "export JIRA_API_TOKEN='your-api-token'"
echo ""
echo "📝 To get your API token:"
echo "1. Go to https://id.atlassian.com/manage-profile/security/api-tokens"
echo "2. Click 'Create API token'"
echo "3. Copy the token and use it as JIRA_API_TOKEN"
echo ""

# Check if environment variables are set
if [[ -z "$JIRA_URL" || -z "$JIRA_EMAIL" || -z "$JIRA_API_TOKEN" ]]; then
    echo "⚠️  Jira environment variables not set. Please configure them first."
    echo ""
    echo "💡 You can create a .env file with:"
    echo "JIRA_URL=https://your-company.atlassian.net"
    echo "JIRA_EMAIL=your-email@company.com"
    echo "JIRA_API_TOKEN=your-api-token"
    echo ""
else
    echo "✅ Jira environment variables are set"
    echo "   JIRA_URL: $JIRA_URL"
    echo "   JIRA_EMAIL: $JIRA_EMAIL"
    echo "   JIRA_API_TOKEN: [hidden]"
fi

echo ""
echo "📦 Installing MCP Jira dependencies..."

# Install required packages
pip3 install --upgrade pip
pip3 install mcp
pip3 install jira
pip3 install python-dotenv

echo ""
echo "🎯 Next Steps:"
echo "1. Set your Jira environment variables (see above)"
echo "2. Test connection: python3 test_jira_connection.py"
echo "3. Run MCP server: python3 start_mcp_jira_server.py"
echo "4. Use your scripts with real MCP connection"
echo ""
echo "✅ Setup script completed!"

