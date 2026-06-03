#!/bin/bash
# Virt RFE quality assessment for CNV or MTV — draft, display, or comment modes.
set -euo pipefail
cd "$(dirname "$0")"
source load_jira_env.sh
python3 .cursor/skills/rfe-quality-check-vme/scripts/assess_virt_rfe.py "$@"
