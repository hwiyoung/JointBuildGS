#!/usr/bin/env bash
# Called only after the B173 priority figures and remaining B173 work finish.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1
cd "$REPO";site=$1
bash scripts/phd/main_rescore_v1/run.sh "setup-$site" setup_site.py "$site"
if [[ ! -f "$OUT/views/$site.json" ]]; then bash scripts/phd/main_rescore_v1/run_gpu.sh "jobs/${site}__views.json" freeze_views.py; fi
mapfile -t jobs < <(python3 - "$OUT/jobs/${site}_index.json" <<'PY'
import json,sys
for j in json.load(open(sys.argv[1]))['jobs']:
 if j['family']=='2DGS' and j['prior']=='ALS':continue
 print(j['key'])
PY
)
for key in "${jobs[@]}"; do
 if [[ ! -f "$OUT/renders/$key/receipt.json" ]]; then bash scripts/phd/main_rescore_v1/run_gpu.sh "jobs/$key.json"; fi
done
for prior in ALS LoD2; do
 key="${site}__${prior}__fusion"
 if [[ ! -f "$OUT/renders/$key/receipt.json" ]]; then bash scripts/phd/main_rescore_v1/run.sh "patch-$key" render_patches.py "$site" "$prior" fusion; fi
done
bash scripts/phd/main_rescore_v1/site_inputs.sh "$site" & input_pid=$!
bash scripts/phd/main_rescore_v1/site_lane.sh "$site" ALS comparison & als_pid=$!
bash scripts/phd/main_rescore_v1/site_lane.sh "$site" LoD2 comparison & lod_pid=$!
wait "$input_pid";wait "$als_pid";wait "$lod_pid"
bash scripts/phd/main_rescore_v1/run.sh "targets-$site" targets.py "$site"
for prior in ALS LoD2; do for family in judgment_mesh oracle; do
 key="${site}__${prior}__${family}"
 if [[ ! -f "$OUT/renders/$key/receipt.json" ]]; then bash scripts/phd/main_rescore_v1/run.sh "patch-$key" render_patches.py "$site" "$prior" "$family"; fi
done; done
bash scripts/phd/main_rescore_v1/site_lane.sh "$site" ALS targets & als_pid=$!
bash scripts/phd/main_rescore_v1/site_lane.sh "$site" LoD2 targets & lod_pid=$!
wait "$als_pid";wait "$lod_pid"
bash scripts/phd/main_rescore_v1/run.sh "reuse-$site" reused_meshes.py "$site"
bash scripts/phd/main_rescore_v1/run.sh "low-cell0-$site" diagnostics.py "$site"
mapfile -t diagnostic_jobs < <(python3 - "$OUT/diagnostics/${site}_jobs.json" <<'PY'
import json,sys
for j in json.load(open(sys.argv[1]))['jobs']:print(j['prior']+' '+j['key']+' '+j['score_key'])
PY
)
for job in "${diagnostic_jobs[@]}"; do
 read -r prior key scorekey <<< "$job"
 if [[ ! -f "$OUT/meshes/$key/train.json" ]]; then bash scripts/phd/main_rescore_v1/run_mesh_safe.sh "jobs/$key.json" train; fi
 if [[ ! -f "$OUT/scores/$scorekey/values.json" ]]; then bash scripts/phd/main_rescore_v1/run_score16.sh "diag-$scorekey" score_mesh.py "$site" "$prior" "$scorekey" "/out/meshes/$key/train.ply"; fi
 bash scripts/phd/main_rescore_v1/run.sh "depth-$key" figures.py diagnostic --key "$key"
done
echo "SITE_COMPLETE $site"
