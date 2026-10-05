#!/usr/bin/env bash
set -euo pipefail
experiment="$(realpath "${1:?experiment directory}")"
phase="${2:?preflight or train}"
alpha="${3:?0 1 4}"
gpu="${4:?0 1}"
case "$phase" in preflight|train) ;; *) exit 2 ;; esac
case "$alpha" in 0|1|4) ;; *) exit 2 ;; esac
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
artifact="/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts"
base="$artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
parent="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
anchor="$base/runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test "$(docker image inspect "$image" --format '{{.Id}}')" = "$image"
exec 9>"/tmp/jbgs-p1-single-view-gpu-$gpu.lock"
flock 9
used="$(nvidia-smi --id="$gpu" --query-gpu=memory.used --format=csv,noheader,nounits)"
if (( used > 1500 )); then
  printf 'GPU %s is occupied (%s MiB); no existing process was stopped.\n' "$gpu" "$used" >&2
  exit 3
fi
output="$experiment/$phase/alpha_$alpha"
test ! -e "$output"
mkdir -p "$output"
config_sha="$(sha256sum "$parent/inputs_v2/experiment.json" | cut -d ' ' -f 1)"
binding_sha="$(sha256sum "$parent/inputs_v2/P1/bindings.json" | cut -d ' ' -f 1)"
mask_sha="$(sha256sum "$experiment/mask/r1_mask.npz" | cut -d ' ' -f 1)"
gate_mount=()
if [[ "$phase" == train ]]; then
  test -s "$experiment/gate.json"
  gate_mount=(--mount "type=bind,src=$experiment/gate.json,dst=/gate.json,readonly")
fi
exec docker run --rm --name "jbgs-p1-weight-$phase-a$alpha-$(basename "$experiment")" \
  --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" \
  --env JBGS_RUNTIME_IMAGE_ID="$image" \
  --env JBGS_MVS_PGSR_MODE=mvs --env JBGS_MVS_REGION=P1 \
  --env JBGS_MVS_CONFIG=/experiment.json --env JBGS_MVS_CONFIG_SHA256="$config_sha" \
  --env JBGS_MVS_BINDING=/mvs/bindings.json --env JBGS_MVS_BINDING_SHA256="$binding_sha" \
  --env JBGS_P1_WEIGHT_MASK=/mask/r1_mask.npz --env JBGS_P1_WEIGHT_MASK_SHA256="$mask_sha" \
  --env JBGS_P1_WEIGHT_MASK_KEY=r1_mask --env JBGS_P1_WEIGHT_ALPHA="$alpha" \
  --env JBGS_P1_WEIGHT_TARGET_CAMERA=DJI_20241217084553_0100_D \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 --env PYTHONDONTWRITEBYTECODE=1 \
  --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 \
  --mount "type=bind,src=$experiment/scripts,dst=/audit,readonly" \
  --mount "type=bind,src=$experiment/parent_scripts,dst=/parent_scripts,readonly" \
  --mount "type=bind,src=$experiment/config.json,dst=/task_config.json,readonly" \
  --mount "type=bind,src=$experiment/source,dst=/source,readonly" \
  --mount "type=bind,src=$experiment/mask,dst=/mask,readonly" \
  --mount "type=bind,src=$parent/inputs_v2/experiment.json,dst=/experiment.json,readonly" \
  --mount "type=bind,src=$base/inputs/P1,dst=/input,readonly" \
  --mount "type=bind,src=$parent/inputs_v2/P1,dst=/mvs,readonly" \
  --mount "type=bind,src=$anchor,dst=/anchor,readonly" \
  --mount "type=bind,src=$base/runtime/weights,dst=/weights,readonly" \
  --mount "type=bind,src=$output,dst=/output" \
  "${gate_mount[@]}" "$image" python /audit/run_phase.py --phase "$phase" --alpha "$alpha"
