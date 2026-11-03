#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1
site=$1
for prior in ALS LoD2; do for family in prior mvs; do
 key="${site}__${prior}__${family}"
 if [[ ! -f "$OUT/scores/$key/values.json" ]]; then bash "$REPO/scripts/phd/main_rescore_v1/run_score16.sh" "input-$key" score_inputs.py "$site" "$prior" "$family"; fi
done; done
