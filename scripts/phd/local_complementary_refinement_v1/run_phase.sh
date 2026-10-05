#!/usr/bin/env bash
# Host orchestration only; all project computation runs inside Docker.
set -euo pipefail
region=${1:?region}
condition=${2:?condition}
phase=${3:?phase}
gpu=${4:?GPU index}
output_relative=${5:-runs/$region/$condition}
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
parent=$(cd -- "$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1" && pwd)
task_root=$(cd -- "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1" && pwd)
[[ $region =~ ^P[123]$ && $condition =~ ^LC_D(005|0005|0)_P(native|release)$ ]]
[[ $phase =~ ^(probe|train|render|metrics)$ && $gpu =~ ^[01]$ ]]
[[ $output_relative != /* && $output_relative != *..* ]]
output="$task_root/$output_relative"
mkdir -p "$output"
if [[ $region == P1 ]]; then
    anchor="$parent/runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000"
else
    anchor="$parent/runs_allocator_v2/$region/D005_Pnative/model/jbgs_complete/iteration_8000"
fi
image_id=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ $(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}') == "$image_id" ]]
exec docker run --rm --name "jbgs-lc-${region}-${condition}-${phase}-$(date +%s)" \
    --network none --gpus "device=$gpu" --cpus 8 --memory 32g --shm-size 4g \
    --user "$(id -u):$(id -g)" \
    -e LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6 -e TORCH_HOME=/weights/torch \
    -e MPLCONFIGDIR=/tmp/geogs-matplotlib -e PYTHONDONTWRITEBYTECODE=1 \
    -e OMP_NUM_THREADS=8 -e OPENBLAS_NUM_THREADS=8 \
    -e PYTORCH_CUDA_ALLOC_CONF=backend:native,max_split_size_mb:128 \
    -e JBGS_RUNTIME_IMAGE_ID="$image_id" \
    -v "$task_root/source:/source:ro" -v "$parent/inputs/$region:/input:ro" \
    -v "$parent/runtime/weights:/weights:ro" -v "$anchor:/anchor:ro" \
    -v "$parent/runs_allocator_v2/$region/${condition#LC_}/train_invocation.json:/parent_invocation.json:ro" \
    -v "$repo/scripts/phd/local_complementary_refinement_v1:/audit:ro" \
    -v "$task_root/contracts/experiment_v1.json:/config.json:ro" \
    -v "$task_root/contracts/input_binding.json:/binding.json:ro" \
    -v "$output:/output" -w /source "$image_id" \
    python /audit/run_phase.py --region "$region" --condition "$condition" --phase "$phase"
