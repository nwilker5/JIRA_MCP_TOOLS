#!/bin/bash
# DRAFT only. Reads a Dataverse CSV; never creates Customer Intelligence links.
# Skill: .cursor/skills/virtstrat-customer-links/SKILL.md
set -euo pipefail
cd "$(dirname "$0")"
if [[ -f jira_mcp_env/bin/activate ]]; then
  # shellcheck disable=SC1091
  source jira_mcp_env/bin/activate
fi
python3 .cursor/skills/virtstrat-customer-links/scripts/copy_customer_links_to_virtstrat.py --draft "$@"
