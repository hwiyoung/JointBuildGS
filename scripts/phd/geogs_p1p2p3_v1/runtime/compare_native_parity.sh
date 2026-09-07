#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
parity_root="$task_root/native_example_parity_v1"
output_root="$parity_root/comparison"
test ! -e "$output_root"
test -s "$parity_root/resumed/model/jbgs_complete/iteration_8100/checkpoint.pth"
mkdir -p "$output_root"
docker run --rm --name jbgs-geogs-native-parity-compare-v1 \
  --network none --cpus 8 --memory 32g --user "$(id -u):$(id -g)" \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  --volume "$repo_root/scripts/phd/geogs_p1p2p3_v1:/audit:ro" \
  --volume "$parity_root/uninterrupted/model:/uninterrupted:ro" \
  --volume "$parity_root/resumed/model:/resumed:ro" \
  --volume "$task_root/native_example_retry_compat_v1/output/model:/native:ro" \
  --volume "$output_root:/output" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  python /audit/runtime/compare_native_parity.py
