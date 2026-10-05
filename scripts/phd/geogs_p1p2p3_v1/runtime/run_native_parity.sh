#!/usr/bin/env bash
set -euo pipefail
mode="${1:?Usage: run_native_parity.sh uninterrupted|resumed}"
case "$mode" in uninterrupted|resumed) ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
image_id=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
output_root="$task_root/native_example_parity_v1/$mode"
test ! -e "$output_root"
mkdir -p "$output_root"
anchor_args=()
if [[ "$mode" == resumed ]]; then
  anchor_path="$task_root/native_example_parity_v1/uninterrupted/model/jbgs_complete/iteration_8000"
  test -s "$anchor_path/checkpoint.pth"
  anchor_args=(--volume "$anchor_path:/anchor:ro")
fi
docker run --rm --name "jbgs-geogs-native-parity-${mode}-v1" \
  --network none --gpus '"device=0"' --cpus 8 --memory 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  --volume "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime:/audit:ro" \
  --volume "$repo_root/configs/phd/geogs_p1p2p3_v1:/config:ro" \
  --volume "$task_root/sources/GeoGS-state-camera-v1:/source:ro" \
  --volume "$task_root/native_example/scene:/scene:ro" \
  --volume "$task_root/native_example/input_manifest.json:/input_manifest.json:ro" \
  --volume "$task_root/runtime/weights:/weights:ro" \
  --volume "$output_root:/output" "${anchor_args[@]}" \
  "$image_id" python /audit/run_native_parity.py --mode "$mode" --config /config/native_example_parity_v1.json
