#!/usr/bin/env bash
# Independent small tiles from the far end of the census queue. The main worker
# reaches these only after the larger eleven tiles and reuses completed files.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$REPO"
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1
for tile in 6911_53361 6907_53360 6907_53359 6908_53362 6910_53360 6908_53358 6910_53361 6909_53363 6910_53359 6911_53362; do
  [[ -f "$OUT/r2/photo_prepared/$tile.complete.json" ]] && continue
  # If the main worker caught up, leave all remaining preparation to it.
  if docker ps --format '{{.Names}}' | rg -q '^jbgs-judgecheck-prep_(6910_53360|6908_53362|6907_53359|6907_53360|6911_53361|6908_53358|6910_53361|6909_53363|6910_53359|6911_53362)$'; then exit 0; fi
  printf '%s\tauxiliary_cpu_preparation\t%s\n' "$(date -Is)" "$tile" >> "$OUT/r2/resources/parallel_preparation.tsv"
  bash scripts/phd/main_judgecheck_v1/run_cpu_reply2_aux.sh "smallprep_$tile" photo_prepare_reply2.py "$tile"
done
