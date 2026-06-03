#!/bin/bash
# Backward-compatible MTV launcher — prefer: ./run_virt_rfe_assessment.sh --project mtv ...
set -euo pipefail
cd "$(dirname "$0")"
exec ./run_virt_rfe_assessment.sh --project mtv "$@"
