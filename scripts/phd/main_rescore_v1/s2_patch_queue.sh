#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
run="$REPO/scripts/phd/main_rescore_v1/run_stage2.sh"
for site in B0_b10 R1rep_b10; do
 for prior in ALS LoD2; do
  for family in fusion judgment_mesh oracle; do
   key="${site}__${prior}__${family}"
   bash "$run" "$key-depth" s2_patches.py "$site" "$prior" "$family"
   bash "$REPO/scripts/phd/main_rescore_v1/s2_build_one.sh" "$key"
  done
 done
done
