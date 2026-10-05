#!/usr/bin/env bash
set -euo pipefail
region="${1:?P1 P2 P3}"
mode="${2:?mvs or mvs_pgsr}"
prior="${3:?0.005 or 0.0005}"
phase="${4:-preflight}"
gpu="${5:-1}"
case "$region" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$mode" in mvs|mvs_pgsr) ;; *) exit 2 ;; esac
case "$prior" in 0.005|0.0005) ;; *) exit 2 ;; esac
case "$phase" in preflight|train) ;; *) exit 2 ;; esac
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
base="$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
task="$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
config="$task/inputs_v2/experiment.json"
binding="$task/inputs_v2/$region/bindings.json"
source_path="$task/sources/GeoGS-mvs-pgsr-v1"
image=jointbuildgs:geogs-official-db40c95-compat-v1
image_id=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test "$(docker image inspect "$image" --format '{{.Id}}')" = "$image_id"
test -s "$config"
test -s "$binding"
test -s "$source_path/mvs_pgsr_source_provenance.json"
cmp -s "$repo/configs/phd/geogs_mvs_pgsr_v1/experiment_v2.json" "$config"
anchor="$base/runs_allocator_v2/$region/D005_Pnative/model/jbgs_complete/iteration_8000"
if [[ "$region" == P1 ]]; then anchor="$base/runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000"; fi
gate_mount=()
if [[ "$phase" == train ]]; then
  test -s "$task/execution_gate_v1.json"
  gate_mount=(--mount "type=bind,src=$task/execution_gate_v1.json,dst=/execution_gate.json,readonly")
fi
mkdir -p "$task/$phase/$region/${mode}_${prior}"
output="$(mktemp -d "$task/$phase/$region/${mode}_${prior}/attempt.XXXXXXXX")"
config_sha="$(sha256sum "$config" | cut -d ' ' -f 1)"
binding_sha="$(sha256sum "$binding" | cut -d ' ' -f 1)"
printf '%s\n' "$output"
exec docker run --rm --name "jbgs-mvs-pgsr-$region-$mode-$phase-$(basename "$output")" \
  --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g \
  --user "$(id -u):$(id -g)" \
  --env JBGS_RUNTIME_IMAGE_ID="$image_id" \
  --env JBGS_MVS_PGSR_MODE="$mode" --env JBGS_MVS_REGION="$region" \
  --env JBGS_MVS_CONFIG=/experiment.json --env JBGS_MVS_CONFIG_SHA256="$config_sha" \
  --env JBGS_MVS_BINDING=/mvs/bindings.json --env JBGS_MVS_BINDING_SHA256="$binding_sha" \
  --env TORCH_HOME=/weights/torch --env MPLCONFIGDIR=/tmp/geogs-matplotlib \
  --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 \
  --env OMP_NUM_THREADS=8 --env OPENBLAS_NUM_THREADS=8 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 \
  --mount "type=bind,src=$repo/scripts/phd/geogs_mvs_pgsr_v1,dst=/audit,readonly" \
  --mount "type=bind,src=$config,dst=/experiment.json,readonly" \
  --mount "type=bind,src=$source_path,dst=/source,readonly" \
  --mount "type=bind,src=$base/inputs/$region,dst=/input,readonly" \
  --mount "type=bind,src=$task/inputs_v2/$region,dst=/mvs,readonly" \
  --mount "type=bind,src=$anchor,dst=/anchor,readonly" \
  --mount "type=bind,src=$base/runtime/weights,dst=/weights,readonly" \
  --mount "type=bind,src=$output,dst=/output" \
  "${gate_mount[@]}" "$image" python /audit/run_phase.py \
  --region "$region" --mode "$mode" --prior "$prior" --phase "$phase"
