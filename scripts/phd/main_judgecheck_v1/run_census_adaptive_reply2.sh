#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$REPO"
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1
mode=$1
[[ "$mode" == roofs || "$mode" == walls ]] || exit 2
bash scripts/phd/main_judgecheck_v1/run_cpu.sh censusplan census_plan_reply2.py
if [[ "$mode" == roofs ]]; then
  while read -r tile; do
    bash scripts/phd/main_judgecheck_v1/run_cpu.sh "prep_$tile" photo_prepare_reply2.py "$tile"
  done < "$OUT/r2/census_tiles.txt"
  groups='0 1'
else
  [[ -f "$OUT/r2/reports/roof_commit.json" ]] || { printf 'Roof report commit receipt required before walls\n'; exit 2; }
  groups='2'
fi
for group in $groups; do
  while read -r tile; do
    [[ -f "$OUT/r2/photo_scores/$tile/complete.json" || -f "$OUT/r2/photo_scores/$tile/group$group/complete.json" ]] && continue
    while true; do
      set +e
      bash scripts/phd/main_judgecheck_v1/run_gpu_guarded_reply2.sh "photo${group}_$tile" photo_score_group_reply2.py "$tile:$group"
      result=$?
      set -e
      [[ "$result" == 0 ]] && break
      [[ "$result" == 3 ]] || exit "$result"
      printf '%s\tCPU_selected_other_research_GPU_active\tgroup%s %s\n' "$(date -Is)" "$group" "$tile" >> "$OUT/r2/resources/cpu_fallback.tsv"
      bash scripts/phd/main_judgecheck_v1/run_cpu.sh "cpu_photo${group}_$tile" photo_score_group_reply2.py "$tile:$group" cpu
      break
    done
  done < "$OUT/r2/census_group${group}_tiles.txt"
  bash scripts/phd/main_judgecheck_v1/run_cpu.sh "photodecide$group" photo_judgment_reply2.py "$group"
  bash scripts/phd/main_judgecheck_v1/run_cpu.sh "judge$group" judgment_reply2.py "$group"
  bash scripts/phd/main_judgecheck_v1/run_cpu.sh "metrics$group" metrics_reply2.py "$group"
done
if [[ "$mode" == roofs ]]; then
  for prior in ALS LoD2; do
    bash scripts/phd/main_judgecheck_v1/run_cpu.sh "maps$prior" figures_reply2.py "$prior"
    bash scripts/phd/main_judgecheck_v1/run_cpu.sh "photos$prior" montage_reply2.py "$prior" roofs
  done
  bash scripts/phd/main_judgecheck_v1/run_cpu.sh roofreport report_reply2.py roofs
  printf 'ROOF_REPORT_READY_FOR_VISUAL_CHECK_AND_COMMIT; continue walls in the same task\n'
else
  bash scripts/phd/main_judgecheck_v1/run_cpu.sh wallphotos montage_reply2.py LoD2 all
  bash scripts/phd/main_judgecheck_v1/run_cpu.sh fullexport export_reply2.py
  bash scripts/phd/main_judgecheck_v1/run_cpu.sh fullreport report_reply2.py full
  printf 'STAGE_A_READY_FOR_FINAL_VALIDATION_AND_DELIVERY; Stage B remains closed\n'
fi
