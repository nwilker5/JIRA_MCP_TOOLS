#!/bin/bash
# Virt RFE quality assessment for CNV or MTV — draft, display, or comment modes.
set -euo pipefail
cd "$(dirname "$0")"
set -a
source .env_wilker_jira
set +a
if [ -d "jira_mcp_env" ]; then
  source jira_mcp_env/bin/activate
fi
python3 assess_virt_rfe.py "$@"
