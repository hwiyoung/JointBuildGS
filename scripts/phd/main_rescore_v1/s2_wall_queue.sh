#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1/addendum3_stage2
site=$1
if [[ ! -f "$OUT/renders/${site}__ALS__oracle_mvswalls/receipt.json" ]]; then
  bash "$REPO/scripts/phd/main_rescore_v1/run_stage2.sh" "$site-wall-depth" s2_walls.py "$site"
fi
for family in fusion judgment_mesh oracle; do
  bash "$REPO/scripts/phd/main_rescore_v1/s2_build_one.sh" "${site}__ALS__${family}_mvswalls"
done
