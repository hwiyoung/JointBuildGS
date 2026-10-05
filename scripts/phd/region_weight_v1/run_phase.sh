#!/usr/bin/env bash
set -euo pipefail
bundle="$(realpath "${1:?bundle}")"
region="${2:?region}"; phase="${3:?phase}"; alpha="${4:?alpha}"; gpu="${5:?gpu}"
case "$region:$phase:$alpha:$gpu" in P[23]:preflight:[014]:[01]|P[23]:train:[014]:[01]) ;; *) exit 2;; esac
artifact=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts
base="$artifact/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
parent="$artifact/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1"
experiment="$bundle/$region"
anchor="$base/runs_allocator_v2/$region/D005_Pnative/model/jbgs_complete/iteration_8000"
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
exec 9>"/tmp/jbgs-p1-single-view-gpu-$gpu.lock"
flock 9
while (( $(nvidia-smi --id="$gpu" --query-gpu=memory.used --format=csv,noheader,nounits) > 1500 )); do sleep 30; done
sha256sum --check --status "$bundle/frozen_files.sha256"
output="$experiment/$phase/alpha_$alpha"; test ! -e "$output"; mkdir -p "$output"
gate=()
if [[ "$phase" == train ]]; then gate=(--mount "type=bind,src=$experiment/gate.json,dst=/gate.json,readonly"); fi
config_sha="$(sha256sum "$parent/inputs_v2/experiment.json" | cut -d ' ' -f 1)"
binding_sha="$(sha256sum "$parent/inputs_v2/$region/bindings.json" | cut -d ' ' -f 1)"
mask_sha="$(sha256sum "$experiment/mask/manifest.json" | cut -d ' ' -f 1)"
command=(docker run --rm --name "jbgs-region-weight-$region-$phase-a$alpha-$(basename "$bundle")"
 --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g --user "$(id -u):$(id -g)"
 -e JBGS_RUNTIME_IMAGE_ID="$image" -e JBGS_MVS_PGSR_MODE=mvs -e JBGS_MVS_REGION="$region"
 -e JBGS_MVS_CONFIG=/experiment.json -e JBGS_MVS_CONFIG_SHA256="$config_sha"
 -e JBGS_MVS_BINDING=/mvs/bindings.json -e JBGS_MVS_BINDING_SHA256="$binding_sha"
 -e JBGS_REGION_WEIGHT_MASK=/mask/manifest.json -e JBGS_REGION_WEIGHT_MASK_SHA256="$mask_sha" -e JBGS_REGION_WEIGHT_ALPHA="$alpha"
 -e TORCH_HOME=/weights/torch -e MPLCONFIGDIR=/tmp/geogs-matplotlib -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
 -e OMP_NUM_THREADS=8 -e OPENBLAS_NUM_THREADS=8 -e PYTHONDONTWRITEBYTECODE=1
 -e PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128
 -v "$bundle/scripts:/audit:ro" -v "$bundle/parent_scripts:/parent_scripts:ro" -v "$bundle/source:/source:ro"
 -v "$experiment/config.json:/task_config.json:ro" -v "$experiment/mask:/mask:ro"
 -v "$parent/inputs_v2/experiment.json:/experiment.json:ro" -v "$parent/inputs_v2/$region:/mvs:ro"
 -v "$base/inputs/$region:/input:ro" -v "$anchor:/anchor:ro" -v "$base/runtime/weights:/weights:ro"
 -v "$output:/output" "${gate[@]}" "$image" python /audit/run_phase.py --phase "$phase" --alpha "$alpha")
printf '%q ' "${command[@]}" > "$output/docker_command.sh"
printf '\n' >> "$output/docker_command.sh"
"${command[@]}"
