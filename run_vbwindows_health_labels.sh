#!/bin/bash
# VBWindows health label sync — uses VME Automation Bot by default.
# Draft by default; use --execute to apply.
set -euo pipefail
cd "$(dirname "$0")"
source load_vme_bot_env.sh
python3 .cursor/skills/vbwindows-health-labels/scripts/vbwindows_health_labels.py "$@"
