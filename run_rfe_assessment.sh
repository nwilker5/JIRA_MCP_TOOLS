#!/bin/bash
# Backward-compatible wrapper — prefer: ./run_virt_rfe_assessment.sh
set -euo pipefail
cd "$(dirname "$0")"
exec ./run_virt_rfe_assessment.sh "$@"
