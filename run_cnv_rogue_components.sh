#!/bin/bash
# CNV rogue component investigation — uses your .env_jira credentials (any team member).
set -euo pipefail
cd "$(dirname "$0")"
source load_jira_env.sh
python3 .cursor/skills/cnv-rogue-components/scripts/cnv_rogue_components.py "$@"
