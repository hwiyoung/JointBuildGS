#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1/addendum3_stage1
run="$REPO/scripts/phd/main_rescore_v1/run_add3.sh"
for prior in ALS LoD2; do
 while [[ ! -f "$OUT/scores/B173nb_b10__${prior}__FINALTRAIN_30000/values.json" ]]; do sleep 30; done
 bash "$run" "check-result-$prior" add3_checks.py "$prior" results
done
bash "$run" lineage-join add3_lineage_join.py
for prior in ALS LoD2; do
 while [[ ! -f "$OUT/scores/B173nb_b10__${prior}__oracle/values.json" ]]; do sleep 30; done
 bash "$run" "quality-$prior" target_quality.py B173nb_b10 "$prior" judgment_mesh "B173nb_b10__${prior}__judgment_mesh"
 bash "$run" "figure-prepare-$prior" add3_figures.py prepare "$prior"
 bash "$run" "figure-draw-$prior" add3_figures.py draw "$prior"
done
