#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1
cd "$REPO"
bash scripts/phd/main_rescore_v1/run.sh reuse-b173 reused_meshes.py B173nb_b10
bash scripts/phd/main_rescore_v1/run.sh low-cell0-b173 diagnostics.py B173nb_b10
for key in B173nb_b10__ALS__r8_30000 B173nb_b10__ALS__baseline_30000 B173nb_b10__LoD2__baseline_30000; do
 prior=ALS; [[ "$key" != *'__LoD2__'* ]] || prior=LoD2
 for mode in train coarse; do
  if [[ "$mode" == coarse ]]; then bash scripts/phd/main_rescore_v1/run_mesh_safe.sh "jobs/$key.json" coarse; fi
  if [[ ! -f "$OUT/scores/${key}__$mode/values.json" ]]; then bash scripts/phd/main_rescore_v1/run_score16.sh "diag-$key-$mode" score_mesh.py B173nb_b10 "$prior" "${key}__$mode" "/out/meshes/$key/$mode.ply"; fi
 done
done
mapfile -t jobs < <(python3 - "$OUT/diagnostics/B173nb_b10_jobs.json" <<'PY'
import json,sys
for j in json.load(open(sys.argv[1]))['jobs']:print(j['prior']+' '+j['key']+' '+j['score_key'])
PY
)
for job in "${jobs[@]}"; do
 read -r prior key scorekey <<< "$job"
 if [[ ! -f "$OUT/scores/$scorekey/values.json" ]]; then bash scripts/phd/main_rescore_v1/run_score16.sh "diag-$scorekey" score_mesh.py B173nb_b10 "$prior" "$scorekey" "/out/meshes/$key/train.ply"; fi
 bash scripts/phd/main_rescore_v1/run.sh "depth-$key" figures.py diagnostic --key "$key"
done
key=B173nb_b10__ALS__fusion_old
if [[ ! -f "$OUT/scores/$key/values.json" ]]; then bash scripts/phd/main_rescore_v1/run_score16.sh score-old-fusion score_mesh.py B173nb_b10 ALS "$key" /art/phase-payloads/phd/main_baselines_v1/PHD-MAIN-BASELINES-v1/runs/B173nb_b10/mvsfuse_ALS/post/mesh_tsdf.ply; fi
bash scripts/phd/main_rescore_v1/run.sh mesh-diagnostic-tables mesh_diagnostics.py
