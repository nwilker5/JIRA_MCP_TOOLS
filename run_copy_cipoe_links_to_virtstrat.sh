#!/bin/bash
# Copy missing CIPOE links from linked CNV issues onto VIRTSTRAT Features.
# Default: dry-run. Pass --execute [--bot] to apply.
set -euo pipefail
cd "$(dirname "$0")"
source jira_mcp_env/bin/activate
python3 .cursor/skills/virtstrat-cipoe-links/scripts/copy_cipoe_links_to_virtstrat.py "$@"
