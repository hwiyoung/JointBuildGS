#!/usr/bin/env bash
set -euo pipefail
REPO=${JBGS_MESHPATCH_REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}
OUT=$(realpath "$REPO/../JointBuildGS-artifacts/phase-payloads/phd/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1")
cd "$REPO"
mapfile -t keys < <(python - <<'PY'
import json
from pathlib import Path
x=json.loads(Path('configs/phd/main_meshpatch_v1/mesh_targets_v1.json').read_text())
rs=sorted(x['targets'],key=lambda r:(0 if r['result'] in ['nojudge_ALS_s0','lt_dynnow_ALS_s0'] else 1,r['site'],r['prior'],r['result']))
for r in rs:print(r['key'],r['status'])
PY
)
for item in "${keys[@]}"; do
  read -r key state <<< "$item"
  if [[ -f "docs/experiments/phd/main_meshpatch_v1/tables/meshes/$key.json" ]]; then continue; fi
  args=()
  if [[ "$state" == READY ]]; then args=(--large); fi
  set +e
  bash scripts/phd/main_meshpatch_v1/run_cpu.sh "mesh-$key" "${args[@]}" mesh_worker.py "$key"
  rc=$?
  set -e
  if (( rc != 0 )); then
    printf '%s\t%s\t%s\n' "$(date -Is)" "$key" "$rc" >> "$OUT/logs/queue_failures.tsv"
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
