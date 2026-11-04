#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
run="$REPO/scripts/phd/main_rescore_v1/run_stage2.sh"
site=$1
for prior in ALS LoD2; do
 for family in baseline_30000 GeoGS_30000 2DGS_30000 CDGS_30000; do
  key="${site}__${prior}__${family}"
  bash "$run" "$key-cleanup" s2_mesh.py cleanup "$key"
  bash "$run" "$key-score" s2_mesh.py score "$key"
 done
done
