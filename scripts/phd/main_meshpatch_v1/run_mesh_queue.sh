#!/usr/bin/env bash
set -euo pipefail
REPO=${JBGS_MESHPATCH_REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}
OUT=$(realpath "$REPO/../JointBuildGS-artifacts/phase-payloads/phd/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1")
cd "$REPO"
if [[ -f configs/phd/main_meshpatch_v1/memory_execution_v1.json && ! -f "$OUT/status/memory_bootstrap_done.json" ]]; then
  # One bounded probe of a previously OOM-killed source. Subsequent runs reuse
  # its stage receipt; mesh_staged refuses an identical failed retry.
  if ! bash scripts/phd/main_meshpatch_v1/run_cpu.sh memory-probe-b0 --large mesh_staged.py B0_b10__ALS__cdgsnofit_ALS_s0 --probe-cleanup; then
    printf '%s\tB0_b10__ALS__cdgsnofit_ALS_s0\tcleanup_failed\n' "$(date -Is)" >> "$OUT/logs/queue_failures.tsv"
  fi
  bash scripts/phd/main_meshpatch_v1/run_cpu.sh memory-bootstrap mesh_memory_plan.py --finish-probe
  bash scripts/phd/main_meshpatch_v1/run_cpu.sh memory-bootstrap-report report.py
fi
axes_ok=0
if [[ -f configs/phd/main_meshpatch_v1/axes_addendum_v1.lock.json ]]; then
  baseline_args=(--large)
  if [[ -f docs/experiments/phd/main_meshpatch_v1/tables/axes_baseline_replay.json ]]; then baseline_args=(); fi
  if bash scripts/phd/main_meshpatch_v1/run_axes.sh axes-baseline "${baseline_args[@]}" axes_worker.py baseline; then
    axes_ok=1
  else
    printf '%s\taxes_baseline\tFAILED\n' "$(date -Is)" >> "$OUT/logs/queue_failures.tsv"
  fi
fi
mapfile -t keys < <(python - <<'PY'
import json
from pathlib import Path
c=Path('configs/phd/main_meshpatch_v1')
x=json.loads((c/'mesh_targets_v1.json').read_text())
a=json.loads((c/'axes_addendum_v1.json').read_text()) if (c/'axes_addendum_v1.json').exists() else {}
i=json.loads((c/'interview_addendum_v2.json').read_text()) if (c/'interview_addendum_v2.json').exists() else None
rs=x['targets']+a.get('extra_targets',[])
first=a.get('stage1_first_keys',[])
def order(r):
    if i:
        if r['key']==i['current_first_key']:return (-3,r['key'])
        if r['result'] in ['nojudge_ALS_s0','lt_dynnow_ALS_s0']:return (-2,r['key'])
    if r['key'] in first:return (0,first.index(r['key']))
    if r['result'] in ['nojudge_ALS_s0','lt_dynnow_ALS_s0']:return (1,r['key'])
    return (2,r['key'])
for r in sorted(rs,key=order):print(r['key'],r['status'])
PY
)
interview_ran=0
for item in "${keys[@]}"; do
  read -r key state <<< "$item"
  if [[ -f configs/phd/main_meshpatch_v1/interview_addendum_v2.json ]] && (( ! interview_ran )); then
    if [[ "$key" != R1rep_b10__ALS__prop_ALS_s1 && "$key" != *__ALS__nojudge_ALS_s0 && "$key" != *__ALS__lt_dynnow_ALS_s0 ]]; then
      bash scripts/phd/main_meshpatch_v1/run_interview_queue.sh
      interview_ran=1
    fi
  fi
  if [[ ! -f "docs/experiments/phd/main_meshpatch_v1/tables/meshes/$key.json" ]]; then
    args=()
    if [[ "$state" == READY ]]; then args=(--large); fi
    if [[ "$state" == READY ]] && ! bash scripts/phd/main_meshpatch_v1/run_cpu.sh "memory-plan-$key" mesh_memory_plan.py --key "$key"; then
      printf '%s\t%s\tresource_deferred\n' "$(date -Is)" "$key" >> "$OUT/logs/queue_failures.tsv"
      continue
    fi
    if ! bash scripts/phd/main_meshpatch_v1/run_cpu.sh "mesh-$key" "${args[@]}" mesh_staged.py "$key"; then
      printf '%s\t%s\tcleanup_failed\n' "$(date -Is)" "$key" >> "$OUT/logs/queue_failures.tsv"
      continue
    fi
  fi
  if (( axes_ok )) && [[ ! -f "docs/experiments/phd/main_meshpatch_v1/tables/axes/$key.json" ]]; then
    args=()
    if [[ "$state" == READY ]]; then args=(--large); fi
    if ! bash scripts/phd/main_meshpatch_v1/run_axes.sh "axes-$key" "${args[@]}" axes_worker.py "$key"; then
      printf '%s\t%s\taxes_failed\n' "$(date -Is)" "$key" >> "$OUT/logs/queue_failures.tsv"
    fi
  fi
  if [[ "$key" == *__ALS__nojudge_ALS_s0 || "$key" == *__ALS__lt_dynnow_ALS_s0 ]]; then
    if ! bash scripts/phd/main_meshpatch_v1/run_cpu.sh case-progress case_figures.py; then
      printf '%s\t%s\tfigure_failed\n' "$(date -Is)" "$key" >> "$OUT/logs/queue_failures.tsv"
    fi
  fi
  if ! bash scripts/phd/main_meshpatch_v1/run_cpu.sh report-progress report.py; then
    printf '%s\t%s\treport_failed\n' "$(date -Is)" "$key" >> "$OUT/logs/queue_failures.tsv"
  fi
done
bash scripts/phd/main_meshpatch_v1/run_cpu.sh case-figures case_figures.py
bash scripts/phd/main_meshpatch_v1/run_cpu.sh report-final report.py
bash scripts/phd/main_meshpatch_v1/run_cpu.sh package-final package.py handover
