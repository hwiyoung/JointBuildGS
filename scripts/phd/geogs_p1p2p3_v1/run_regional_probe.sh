#!/usr/bin/env bash
set -euo pipefail
region="${1:?Usage: run_regional_probe.sh P1|P2|P3 0|1}"
gpu="${2:?GPU index 0 or 1}"
case "$region" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
source "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime_paths.sh"
output_root="$parity_root/$region/restore_probe"
test -s "$anchor_root/checkpoint.pth"
test -s "$anchor_root/point_cloud.ply"
test -s "$anchor_root/receipt.json"
test -s "$baseline_root/train_invocation.json"
test ! -e "$output_root"
mkdir -p "$output_root"
image_id=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
docker run --rm --name "jbgs-geogs-${region}-actual-restore-${runtime_revision}" \
  --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" \
  --env JBGS_RUNTIME_IMAGE_ID="$image_id" \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  --volume "$repo_root/scripts/phd/geogs_p1p2p3_v1:/audit:ro" \
  --volume "$task_root/sources/GeoGS-state-camera-v1:/source:ro" \
  --volume "$task_root/inputs/$region:/input:ro" \
  --volume "$task_root/runtime/weights:/weights:ro" \
  --volume "$baseline_root/train_invocation.json:/invocation.json:ro" \
  --volume "$anchor_root:/anchor:ro" --volume "$output_root:/output" \
  "${runtime_env[@]}" "${runtime_mounts[@]}" \
  "$image_id" python /audit/runtime/prepare_regional_probe.py > "$output_root/probe.log" 2>&1
