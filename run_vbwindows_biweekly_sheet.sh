#!/bin/bash
# VBWindows biweekly executive briefs → Google Sheet (personal Jira + personal gws).
set -euo pipefail
cd "$(dirname "$0")"

SCRIPT=".cursor/skills/vbwindows-biweekly-sheet/scripts/vbwindows_biweekly_sheet.py"

# Personal credentials only — do not fall back to another user's env files.
if [[ -f .env_jira ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env_jira
  set +a
elif [[ -z "${JIRA_URL:-}" || -z "${JIRA_API_TOKEN:-}" ]]; then
  if [[ "${1:-}" == "fetch" ]]; then
    echo "No .env_jira found. Copy .cursor/skills/vbwindows-biweekly-sheet/env.jira.example" >&2
    echo "to .env_jira with YOUR Jira credentials (do not use someone else's file)." >&2
    exit 1
  fi
fi

# Activate venv if present
if [[ -f jira_mcp_env/bin/activate ]]; then
  # shellcheck disable=SC1091
  source jira_mcp_env/bin/activate
fi

python3 "$SCRIPT" "$@"
