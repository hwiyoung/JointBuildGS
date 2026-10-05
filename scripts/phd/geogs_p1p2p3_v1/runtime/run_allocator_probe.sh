#!/usr/bin/env bash
set -euo pipefail
gpu="${1:?Usage: run_allocator_probe.sh 0|1}"
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
baseline_root="$task_root/runs/P1/D005_Pnative"
anchor_root="$baseline_root/model/jbgs_complete/iteration_8000"
output_root="$task_root/runtime/allocator_recovery_v2/P1_native128"
for required in checkpoint.pth point_cloud.ply receipt.json; do
  test -s "$anchor_root/$required"
done
test -s "$baseline_root/train_invocation.json"
test ! -e "$output_root"
mkdir -p "$output_root"
image_id=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
docker run --rm --name jbgs-geogs-P1-allocator-native128-probe-v2 \
  --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" \
  --env JBGS_RUNTIME_IMAGE_ID="$image_id" \
  --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  --volume "$repo_root/scripts/phd/geogs_p1p2p3_v1:/audit:ro" \
  --volume "$task_root/sources/GeoGS-state-camera-v1:/source:ro" \
  --volume "$task_root/inputs/P1:/input:ro" \
  --volume "$task_root/runtime/weights:/weights:ro" \
  --volume "$baseline_root/train_invocation.json:/invocation.json:ro" \
  --volume "$anchor_root:/anchor:ro" --volume "$output_root:/output" \
  "$image_id" python /audit/runtime/probe_allocator_restore.py > "$output_root/probe.log" 2>&1
