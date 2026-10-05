#!/usr/bin/env bash
set -euo pipefail
geogs_vv_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_vv_task=$(realpath "$geogs_vv_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_vv_exp="$geogs_vv_task/no_anchor_sfm_memory_recovery_v2"
geogs_vv_out="$geogs_vv_exp/validation/runtime_cuda_v1"
geogs_vv_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test ! -e "$geogs_vv_out"
mkdir -p -- "$geogs_vv_out"
cp -- "${BASH_SOURCE[0]}" "$geogs_vv_out/launcher.sh"
cat > "$geogs_vv_out/resource_deviation_before_fixture.json" <<'JSON'
{"scientific_verdict": null, "training_processes_stopped_or_changed": false,
 "temporary_additional_gpu_process": 1, "gpu_allocator_cap_bytes": 67108864,
 "cuda_driver_context_excluded": true, "host_container_limit_bytes": 4294967296,
 "synthetic_optimizer_steps": 8, "training_inputs_or_reference_mounted": false,
 "resource_deviation": "One bounded tiny CUDA lifecycle fixture temporarily exceeds two GPU processes; existing training remains unchanged and timing may be perturbed.",
 "purpose": "Validate exact Adam state, parameter, growth/prune lifecycle and pinned runtime before any replacement decision."}
JSON
nvidia-smi --query-gpu=timestamp,index,uuid,memory.used,memory.free,utilization.gpu --format=csv > "$geogs_vv_out/gpu_before.csv"
trap 'geogs_vv_exit=$?; printf "%s\n" "$geogs_vv_exit" > "$geogs_vv_out/exit_code.txt"' EXIT
docker run --rm --network none --gpus device=0 --cpus 1 --memory 4g --memory-swap 4g \
  --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$geogs_vv_exp/source,dst=/source,readonly" \
  --mount "type=bind,src=$geogs_vv_exp/preparation_runtime,dst=/work,readonly" \
  --mount "type=bind,src=$geogs_vv_out,dst=/out" \
  "$geogs_vv_image" /opt/geogs/bin/python /work/memory_recovery_v2/verify_runtime.py \
  --prepared-source /source --v1-directory /work/memory_recovery_v1 --device cuda --receipt /out/receipt.json \
  > "$geogs_vv_out/stdout.log" 2> "$geogs_vv_out/stderr.log"
nvidia-smi --query-gpu=timestamp,index,uuid,memory.used,memory.free,utilization.gpu --format=csv > "$geogs_vv_out/gpu_after.csv"
cat "$geogs_vv_out/stdout.log"
