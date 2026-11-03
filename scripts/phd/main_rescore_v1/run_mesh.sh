#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1"
job=$1;mode=${2:-final}
key=$(python3 - "$OUT/$job" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['key'])
PY
)
if [[ -f "$OUT/meshes/$key/$mode.json" ]]; then exit 0; fi
if [[ ! -f "$OUT/meshes/$key/${mode}_work/inputs/meta.json" ]]; then
 bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "${mode}prep" mesh_pipeline.py "/out/$job" "$mode" prepare
fi
if [[ ! -f "$OUT/meshes/$key/${mode}_work/order/order.json" ]]; then
 bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "${mode}plan" mesh_pipeline.py "/out/$job" "$mode" plan
fi
n=$(python3 - "$OUT/meshes/$key/${mode}_work/plan/layout.json" <<'PY'
import json,sys
print(len(json.load(open(sys.argv[1]))['tiles']))
PY
)
for ((i=0;i<n;i++)); do
 if [[ ! -f "$OUT/meshes/$key/${mode}_work/tiles/tile$i.json" ]]; then
  bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "${mode}tile$i" mesh_pipeline.py "/out/$job" "$mode" tile "$i"
 fi
done
if [[ ! -f "$OUT/meshes/$key/${mode}_work/merged.json" ]]; then
 bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "${mode}merge" mesh_pipeline.py "/out/$job" "$mode" merge
fi
bash "$REPO/scripts/phd/main_rescore_v1/run.sh" "${mode}finish" mesh_pipeline.py "/out/$job" "$mode" finish
