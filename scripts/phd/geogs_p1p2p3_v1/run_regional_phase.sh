#!/usr/bin/env bash
set -euo pipefail
region="${1:?region P1 P2 P3}"
condition="${2:?condition ID}"
phase="${3:?train parity render metrics auxiliary}"
gpu="${4:-1}"
repeat_contract="${5:-}"
case "$region" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$condition" in D005_Pnative|D0005_Pnative|D0_Pnative|D005_Prelease|D0005_Prelease|D0_Prelease) ;; *) exit 2 ;; esac
case "$phase" in train|parity|render|metrics|auxiliary) ;; *) exit 2 ;; esac
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
source "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime_paths.sh"
image_tag=jointbuildgs:geogs-official-db40c95-compat-v1
image_id=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test "$(docker image inspect "$image_tag" --format '{{.Id}}')" = "$image_id"
test -s "$task_root/inputs/$region/input_manifest.json"
run_path="$runs_root/$region/$condition"
repeat_mounts=()
repeat_env=()
repeat_suffix=""
if [[ -n "$repeat_contract" ]]; then
  test "$runtime_revision" = allocator_v2
  test "$condition" = D005_Pnative
  test "$phase" != parity
  test "$(realpath "$repeat_contract")" = "$(realpath "$task_root/contracts/supplemental_repeat_v1.json")"
  cmp -s "$repeat_contract" "$repo_root/configs/phd/geogs_p1p2p3_v1/supplemental_repeat_v1.json"
  repeat_id=native_repeat_1
  repeat_sha="$(sha256sum "$repeat_contract" | cut -d ' ' -f 1)"
  test -s "$parity_root/$region/anchor_gate.json"
  run_path="$task_root/native_repeat_allocator_v2/$region/$condition"
  repeat_suffix="-$repeat_id"
  repeat_mounts=(--mount "type=bind,src=$repeat_contract,dst=/repeat_contract.json,readonly"
                 --mount "type=bind,src=$parity_root/$region/anchor_gate.json,dst=/anchor_gate.json,readonly")
  repeat_env=(--env JBGS_REPEAT_ID="$repeat_id" --env JBGS_REPEAT_CONTRACT_SHA256="$repeat_sha")
fi
if [[ "$phase" == parity ]]; then run_path="$parity_root/$region/restart"; fi
if [[ "$phase" == train || "$phase" == parity ]]; then
  test ! -e "$run_path"
fi
mkdir -p "$run_path"
mounts=(--mount "type=bind,src=$repo_root/scripts/phd/geogs_p1p2p3_v1,dst=/audit,readonly"
        --mount "type=bind,src=$task_root/contracts/execution_v1.json,dst=/config.json,readonly"
        --mount "type=bind,src=$task_root/sources/GeoGS-state-camera-v1,dst=/source,readonly"
        --mount "type=bind,src=$task_root/inputs/$region,dst=/input,readonly"
        --mount "type=bind,src=$task_root/runtime/weights,dst=/weights,readonly"
        --mount "type=bind,src=$run_path,dst=/output")
if [[ -n "$repeat_contract" || "$condition" != D005_Pnative || "$phase" == parity || ( "$runtime_revision" == allocator_v2 && "$region" == P1 ) ]]; then
  anchor="$anchor_root"
  test -s "$anchor/checkpoint.pth"
  mounts+=(--mount "type=bind,src=$anchor,dst=/anchor,readonly")
fi
exec docker run --rm --name "jbgs-geogs-${region}-${condition}-${phase}-${runtime_revision}${repeat_suffix}" \
  --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" \
  --env JBGS_RUNTIME_IMAGE_ID="$image_id" \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  "${runtime_env[@]}" "${runtime_mounts[@]}" "${repeat_env[@]}" "${repeat_mounts[@]}" "${mounts[@]}" "$image_tag" python /audit/run_regional_phase.py \
  --config /config.json --region "$region" --condition "$condition" --phase "$phase"
