#!/usr/bin/env bash
# Both CPU runners hold the same per-tile lock. Keep the already running
# unlocked initial large tile (6908_53360) exclusively with the main worker.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$REPO"
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1
for tile in 6911_53362 6910_53359 6909_53363 6910_53361 6908_53358 6909_53360 6911_53363 6909_53358 6908_53361 6909_53362 6910_53362 6910_53363 6909_53361; do
  [[ -f "$OUT/r2/photo_prepared/$tile.complete.json" ]] && continue
  printf '%s\tauxiliary_cpu_preparation_tile_lock\t%s\n' "$(date -Is)" "$tile" >> "$OUT/r2/resources/parallel_preparation.tsv"
  bash scripts/phd/main_judgecheck_v1/run_cpu_reply2_aux.sh "auxprep_$tile" photo_prepare_reply2.py "$tile"
done
