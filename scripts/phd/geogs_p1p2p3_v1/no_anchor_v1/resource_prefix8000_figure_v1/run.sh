#!/usr/bin/env bash
set -euo pipefail
figure_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../../.." && pwd)
figure_task=$(realpath "$figure_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
figure_out="$figure_task/evaluation/no_anchor_sfm_v1/resource_prefix8000_figure_v1"
test ! -e "$figure_out"
mkdir -p "$figure_out/execution"
cp -- "$(dirname -- "${BASH_SOURCE[0]}")/build.py" "${BASH_SOURCE[0]}" "$figure_out/execution/"
cp -- "$figure_repo/configs/phd/geogs_p1p2p3_v1/resource_prefix8000_figure_v1.json" "$figure_out/execution/config.json"
declare -A figure_als=([P1]=runs/P1/D005_Pnative [P2]=runs_allocator_v2/P2/D005_Pnative [P3]=runs_allocator_v2/P3/D005_Pnative)
declare -A figure_sfm=([P1]=no_anchor_sfm_memory_recovery_v2 [P2]=no_anchor_sfm_memory_recovery_P2_v2 [P3]=no_anchor_sfm_memory_recovery_P3_v3)
figure_mounts=(--mount "type=bind,src=$figure_out/execution,dst=/code,readonly"
 --mount "type=bind,src=$figure_task/contracts/runtime_layout_allocator_v2.json,dst=/layout.json,readonly"
 --mount "type=bind,src=$figure_task/contracts/sfm_prefix8000_diagnostic_v1.json,dst=/policy.json,readonly"
 --mount "type=bind,src=$figure_task/sources/GeoGS-state-camera-v1/scene/gaussian_model.py,dst=/native_gaussian_model.py,readonly")
for figure_region in P1 P2 P3; do
  for figure_kind in als sfm; do
    if [[ "$figure_kind" == als ]]; then
      figure_run="$figure_task/${figure_als[$figure_region]}"
      figure_invocation=train_invocation.json
      figure_receipt=train_receipt.json
      figure_mounts+=(--mount "type=bind,src=$figure_run/model/input.ply,dst=/inputs/$figure_region/als/input.ply,readonly"
        --mount "type=bind,src=$figure_task/inputs/$figure_region/initialization/lod2_pcd.ply,dst=/inputs/$figure_region/als/canonical_initialization.ply,readonly")
    else
      figure_experiment="$figure_task/${figure_sfm[$figure_region]}"
      figure_run="$figure_experiment/runs/$figure_region/SFM_noanchor_D005_Pnative"
      figure_invocation=invocation.json
      figure_receipt=receipt.json
      figure_mounts+=(--mount "type=bind,src=$figure_run/model/jbgs_no_anchor/initialization.json,dst=/inputs/$figure_region/sfm/initialization.json,readonly"
        --mount "type=bind,src=$figure_run/model/jbgs_no_anchor/first_step.json,dst=/inputs/$figure_region/sfm/first_step.json,readonly"
        --mount "type=bind,src=$figure_experiment/inputs/$figure_region/initialization_manifest.json,dst=/inputs/$figure_region/sfm/sfm_manifest.json,readonly"
        --mount "type=bind,src=$figure_experiment/source/jbgs_memory_recovery_receipt.json,dst=/inputs/$figure_region/sfm/memory_runtime_receipt.json,readonly")
    fi
    figure_mounts+=(--mount "type=bind,src=$figure_run/model/jbgs_trace.jsonl,dst=/inputs/$figure_region/$figure_kind/trace.jsonl,readonly"
      --mount "type=bind,src=$figure_run/$figure_invocation,dst=/inputs/$figure_region/$figure_kind/invocation.json,readonly"
      --mount "type=bind,src=$figure_run/model/jbgs_complete/iteration_8000/receipt.json,dst=/inputs/$figure_region/$figure_kind/complete_receipt.json,readonly"
      --mount "type=bind,src=$figure_run/model/jbgs_complete/iteration_8000/checkpoint.pth,dst=/inputs/$figure_region/$figure_kind/checkpoint.pth,readonly"
      --mount "type=bind,src=$figure_run/model/jbgs_complete/iteration_8000/point_cloud.ply,dst=/inputs/$figure_region/$figure_kind/complete.ply,readonly")
    if [[ -f "$figure_run/$figure_receipt" ]]; then
      figure_mounts+=(--mount "type=bind,src=$figure_run/$figure_receipt,dst=/inputs/$figure_region/$figure_kind/train_receipt.json,readonly")
    fi
  done
done
figure_command=(docker run --rm --network none --cpus 2 --memory 2g --memory-swap 2g --pids-limit 256
 --env NVIDIA_VISIBLE_DEVICES=void --env OMP_NUM_THREADS=2 --env OPENBLAS_NUM_THREADS=2 --env PYTHONDONTWRITEBYTECODE=1
 --env MPLCONFIGDIR=/tmp/matplotlib --user "$(id -u):$(id -g)" "${figure_mounts[@]}"
 --mount "type=bind,src=$figure_out,dst=/out"
 sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
 /opt/geogs/bin/python /code/build.py --config /code/config.json --out /out)
printf '%q ' "${figure_command[@]}" > "$figure_out/execution/command.sh"
printf '\n' >> "$figure_out/execution/command.sh"
trap 'figure_exit=$?; printf "%s\n" "$figure_exit" > "$figure_out/execution/exit_code.txt"' EXIT
"${figure_command[@]}" > "$figure_out/execution/stdout.log" 2> "$figure_out/execution/stderr.log"
cat "$figure_out/execution/stdout.log"
