#!/usr/bin/env bash
set -euo pipefail
region="${1:?P1 P2 P3}"
stage="${2:?geometry renders}"
gpu="${3:-1}"
runtime_args=()
if (( $# > 3 )); then
  extra_args=("${@:4}")
  [[ $(( ${#extra_args[@]} % 2 )) == 0 ]]
  declare -A supplied=()
  for ((i=0; i<${#extra_args[@]}; i+=2)); do
    flag="${extra_args[$i]}"
    value="${extra_args[$((i+1))]}"
    [[ "$flag" == --runtime-layout || "$flag" == --repeat-contract || "$flag" == --resource-contract ]]
    [[ "$value" == /task/contracts/* && -z "${supplied[$flag]:-}" ]]
    supplied[$flag]=1
    runtime_args+=("$flag" "$value")
  done
fi
case "$region" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$stage" in geometry|renders) ;; *) exit 2 ;; esac
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
artifact_root="$repo_root/../JointBuildGS-artifacts"
task_root="$artifact_root/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
test -s "$task_root/contracts/candidates_sealed_v1.json"
mounts=(--mount "type=bind,src=$repo_root/scripts/phd/geogs_p1p2p3_v1/evaluation,dst=/audit,readonly"
  --mount "type=bind,src=$repo_root/scripts/phd/geogs_p1p2p3_v1/resource_contract.py,dst=/audit/resource_contract.py,readonly"
  --mount "type=bind,src=$task_root,dst=/task"
  --mount "type=bind,src=$task_root/sources/GeoGS-state-camera-v1,dst=/source,readonly"
  --mount "type=bind,src=$task_root/runtime/weights,dst=/weights,readonly")
if [[ "$stage" == geometry ]]; then
  reference="$artifact_root/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run/$region/reference.npz"
  mounts+=(--mount "type=bind,src=$reference,dst=/reference/$region/reference.npz,readonly")
fi
docker run --rm --name "jbgs-geogs-${region}-evaluate-${stage}-v1" \
  --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  "${mounts[@]}" jointbuildgs:geogs-official-db40c95-compat-v1 \
  python /audit/run_evaluation.py --task /task --region "$region" --stage "$stage" "${runtime_args[@]}"
