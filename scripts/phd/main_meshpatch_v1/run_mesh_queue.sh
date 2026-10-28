#!/usr/bin/env bash
set -euo pipefail
REPO=${JBGS_MESHPATCH_REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}
OUT=$(realpath "$REPO/../JointBuildGS-artifacts/phase-payloads/phd/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1")
cd "$REPO"
axes_ok=0
if [[ -f configs/phd/main_meshpatch_v1/axes_addendum_v1.lock.json ]]; then
  if bash scripts/phd/main_meshpatch_v1/run_axes.sh axes-baseline --large axes_worker.py baseline; then
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
rs=x['targets']+a.get('extra_targets',[])
first=a.get('stage1_first_keys',[])
def order(r):
    if r['key'] in first:return (0,first.index(r['key']))
    if r['result'] in ['nojudge_ALS_s0','lt_dynnow_ALS_s0']:return (1,r['key'])
    return (2,r['key'])
for r in sorted(rs,key=order):print(r['key'],r['status'])
PY
)
for item in "${keys[@]}"; do
  read -r key state <<< "$item"
  if [[ ! -f "docs/experiments/phd/main_meshpatch_v1/tables/meshes/$key.json" ]]; then
    args=()
    if [[ "$state" == READY ]]; then args=(--large); fi
    if ! bash scripts/phd/main_meshpatch_v1/run_cpu.sh "mesh-$key" "${args[@]}" mesh_worker.py "$key"; then
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
