#!/usr/bin/env bash
set -euo pipefail
phase="${1:?Usage: bash run_native_phase.sh train|render|metrics [native|compat]}"
variant="${2:-native}"
case "$phase" in train|render|metrics) ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
image_tag=jointbuildgs:geogs-official-db40c95-v1
expected_image=sha256:6886d5920db3dc7dc9176b235a8a9240ebaccd607440f09fd7da32c106f2aee6
config_file=native_example_v1.json
output_root="$task_root/native_example/output"
case "$variant" in
  native) ;;
  compat)
    image_tag=jointbuildgs:geogs-official-db40c95-compat-v1
    expected_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
    config_file=native_example_compat_v1.json
    output_root="$task_root/native_example_retry_compat_v1/output"
    ;;
  *) exit 2 ;;
esac
test "$(docker image inspect "$image_tag" --format '{{.Id}}')" = "$expected_image"
test -s "$task_root/native_example/input_manifest.json"
test -s "$task_root/runtime/weights/manifest.json"
test -s "$task_root/runtime/native_gradient_probe.json"
test -z "$(git -C "$task_root/sources/GeoGS" status --porcelain)"
mkdir -p "$output_root"
loader_args=()
if [[ "$phase" != train ]]; then
  # ICU from the isolated Python environment needs that environment's libstdc++.
  # The initial native training environment remains unchanged for parity.
  loader_args=(--env LD_LIBRARY_PATH=/opt/geogs/lib:/usr/local/cuda/lib64:/usr/local/nvidia/lib:/usr/local/nvidia/lib64)
fi
# Evaluation references are intentionally absent from these container mounts.
docker run --rm --name "jbgs-geogs-native-example-${phase}-${variant}-v1" \
  --network none --gpus '"device=1"' --cpus 8 --memory 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  "${loader_args[@]}" \
  --volume "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime:/audit:ro" \
  --volume "$repo_root/configs/phd/geogs_p1p2p3_v1:/config:ro" \
  --volume "$task_root/sources/GeoGS:/source:ro" \
  --volume "$task_root/native_example/scene:/scene:ro" \
  --volume "$task_root/runtime/weights:/weights:ro" \
  --volume "$output_root:/output" \
  "$image_tag" python /audit/run_native_phase.py --phase "$phase" --config "/config/$config_file"
