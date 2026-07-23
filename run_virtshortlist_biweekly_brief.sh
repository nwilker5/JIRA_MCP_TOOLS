#!/bin/bash
# VirtShortList biweekly executive brief — draft (personal) or execute (VME bot).
set -euo pipefail
cd "$(dirname "$0")"

SCRIPT=".cursor/skills/virtshortlist-biweekly-brief/scripts/virtshortlist_biweekly_brief.py"

if [[ "${1:-draft}" == "execute" ]]; then
  source load_vme_bot_env.sh
else
  if [[ -f .env_jira ]]; then
    source load_jira_env.sh 2>/dev/null || source .env_jira
  elif [[ -f .env_wilker_jira ]]; then
    set -a && source .env_wilker_jira && set +a
  else
    echo "No .env_jira found — draft fetch needs personal credentials." >&2
    exit 1
  fi
  source jira_mcp_env/bin/activate 2>/dev/null || true
fi

python3 "$SCRIPT" "$@"
