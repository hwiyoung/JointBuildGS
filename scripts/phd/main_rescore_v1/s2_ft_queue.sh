#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1/addendum3_stage2
DOC="$REPO/docs/experiments/phd/main_rescore_v1/addendum3_stage2"
run="$REPO/scripts/phd/main_rescore_v1/run_stage2.sh"
site=$1;prior=$2;key="${site}__${prior}__FINALTRAIN_30000"
if [[ ! -f "$OUT/jobs/$key.json" ]]; then bash "$run" "$key-bind" s2_ft_bind.py "$site" "$prior"; fi
if [[ ! -f "$OUT/renders/$key/receipt.json" ]]; then bash "$REPO/scripts/phd/main_rescore_v1/run_stage2_gpu.sh" "addendum3_stage2/jobs/$key.json" s2_render_ft.py; fi
bash "$REPO/scripts/phd/main_rescore_v1/s2_build_one.sh" "$key"
if [[ ! -f "$DOC/tables/${site}__check_a_judgment_cell_${prior}.json" ]]; then bash "$run" "$key-targets" s2_checks.py "$site" "$prior" targets; fi
if [[ ! -f "$DOC/tables/target_quality_$key.json" ]]; then bash "$run" "$key-results" s2_checks.py "$site" "$prior" results; fi
if [[ "$prior" == LoD2 && ! -f "$OUT/lineage/$site/join.json" ]]; then
 n=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["points"])' "$OUT/checks/${site}__check_b_selection.json")
 if ((n>0)); then
  if [[ ! -f "$OUT/lineage/$site/receipt.json" ]]; then bash "$REPO/scripts/phd/main_rescore_v1/run_stage2_gpu.sh" "addendum3_stage2/jobs/$key.json" s2_lineage.py; fi
  bash "$run" "$site-lineage-join" s2_lineage.py join "$site"
 else
  bash "$run" "$site-empty-lineage" s2_no_far_points.py "$site"
 fi
fi
