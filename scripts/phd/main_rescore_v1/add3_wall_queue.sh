#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1/addendum3_stage1
run="$REPO/scripts/phd/main_rescore_v1/run_add3.sh"
for family in fusion judgment_mesh oracle; do
 key="B173nb_b10__ALS__${family}_mvswalls"
 job="/out/addendum3_stage1/jobs/$key.json";wd="$OUT/meshes/$key/train_work"
 if [[ ! -f "$OUT/meshes/$key/primary.json" ]]; then
  if [[ ! -f "$wd/inputs/meta.json" ]]; then bash "$run" "$key-prep" add3_train_pipeline.py "$job" train prepare; fi
  if [[ ! -f "$wd/order/order.json" ]]; then bash "$run" "$key-plan" mesh_pipeline.py "$job" train plan; fi
  n=$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))["tiles"]))' "$wd/plan/layout.json")
  for ((i=0;i<n;i++)); do
   if [[ ! -f "$wd/tiles/tile$i.json" ]]; then bash "$run" "$key-tile$i" mesh_pipeline.py "$job" train tile "$i"; fi
  done
  if [[ ! -f "$wd/merged.json" ]]; then bash "$run" "$key-merge" bounded_merge.py "/out/addendum3_stage1/meshes/$key/train_work" "/out/addendum3_stage1/meshes/$key/train_work/merged.ply" "/out/addendum3_stage1/meshes/$key/train_work/merged.json" train; fi
  bash "$run" "$key-cleanup" add3_mesh.py cleanup "$key"
 fi
 bash "$run" "$key-score" add3_mesh.py score "$key"
done
