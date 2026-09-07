#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
run_name="${1:-restore_probe}"
case "$run_name" in restore_probe|restore_probe_retry_v1|restore_probe_retry_v2) ;; *) exit 2 ;; esac
output_root="$task_root/native_example_parity_v1/$run_name"
anchor_root="$task_root/native_example_parity_v1/uninterrupted/model/jbgs_complete/iteration_8000"
test -s "$anchor_root/checkpoint.pth"
test -s "$anchor_root/point_cloud.ply"
test -s "$anchor_root/receipt.json"
test ! -e "$output_root"
mkdir -p "$output_root"
docker run --rm --name jbgs-geogs-native-actual-restore-v1 \
  --network none --gpus '"device=0"' --cpus 8 --memory 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  --volume "$repo_root/scripts/phd/geogs_p1p2p3_v1:/audit:ro" \
  --volume "$repo_root/configs/phd/geogs_p1p2p3_v1:/config:ro" \
  --volume "$task_root/sources/GeoGS-state-camera-v1:/source:ro" \
  --volume "$task_root/native_example/scene:/scene:ro" \
  --volume "$task_root/native_example/input_manifest.json:/input_manifest.json:ro" \
  --volume "$task_root/runtime/weights:/weights:ro" \
  --volume "$anchor_root:/anchor:ro" --volume "$output_root:/output" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  python /audit/runtime/probe_actual_restore.py > "$output_root/probe.log" 2>&1
