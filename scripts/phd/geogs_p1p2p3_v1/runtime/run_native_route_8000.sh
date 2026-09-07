#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
output_root="$task_root/native_example_route_8000_v1"
test ! -e "$output_root"
mkdir -p "$output_root"
docker run --rm --name jbgs-geogs-native-route-8000-v1 \
  --network none --gpus '"device=0"' --cpus 8 --memory 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  --volume "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime:/audit:ro" \
  --volume "$repo_root/configs/phd/geogs_p1p2p3_v1:/config:ro" \
  --volume "$task_root/sources/GeoGS:/source:ro" \
  --volume "$task_root/native_example/scene:/scene:ro" \
  --volume "$task_root/runtime/weights:/weights:ro" \
  --volume "$task_root/native_example_retry_compat_v1/output/model:/checkpoint:ro" \
  --volume "$output_root:/output" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  python /audit/run_native_route_8000.py
