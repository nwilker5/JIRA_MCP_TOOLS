#!/bin/bash
# PX upgrade shortlist pool fetch — uses your .env_jira credentials (any team member).
# Output is the raw keyword pool; the agent curates/classifies per the skill.
set -euo pipefail
cd "$(dirname "$0")"
source load_jira_env.sh
python3 .cursor/skills/px-upgrade-shortlist/scripts/px_upgrade_pool.py "$@"
