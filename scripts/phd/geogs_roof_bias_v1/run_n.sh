#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
art=$(realpath "$repo/../JointBuildGS-artifacts")
task="$art/phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921"
old="$art/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test "$(git -C "$task/sources/GeoGS" rev-parse HEAD)" = db40c95c657ec03ff21c83cb99cf39f4e90247a6
test -z "$(git -C "$task/sources/GeoGS" status --porcelain)"
cp "$repo/scripts/phd/geogs_roof_bias_v1/observe_train.py" "$task/scripts/"
docker run -d --name jbgs-geogs-roof-bias-n-20260921 --gpus '"device=1"' \
  --network none --cpus 8 --shm-size 4g --user "$(id -u):$(id -g)" \
  -e TORCH_HOME=/weights/torch -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS=8 -e OPENBLAS_NUM_THREADS=8 \
  -e PYTHONUNBUFFERED=1 -e GEOGS_SOURCE=/source -e GEOGS_OBSERVATIONS=/output/observations \
  -v "$task/sources/GeoGS:/source:ro" -v "$task/scripts:/audit:ro" \
  -v "$old/native_example/scene:/scene:ro" -v "$old/runtime/weights:/weights:ro" \
  -v "$task/conditions/N:/output" -w /source "$image" \
  bash -c 'date -Iseconds > /output/started.txt; python /audit/observe_train.py -s /scene -m /output/model --lod_depth_path /scene/lod2_prior --da_depth_path /scene/da3_prior --lod2_pcd_path /scene/lod2_pcd.ply --eval --lod_init --freeze_onlybldg --protect_bldg --dynamic_depth_weight > /output/train.log 2>&1; rc=$?; echo "$rc" > /output/train.exit; date -Iseconds > /output/finished.txt; exit "$rc"'
