#!/usr/bin/env bash
# Brief storage-only measurement; preserve both training processes and services.
set -euo pipefail
geogs_tp_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_tp_task=$(realpath "$geogs_tp_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_tp_out="$geogs_tp_task/no_anchor_sfm_memory_recovery_v1/validation/transfer_probe_v1"
geogs_tp_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test ! -e "$geogs_tp_out"
mkdir -p -- "$geogs_tp_out"
cp -- "$geogs_tp_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1/memory_recovery_v2/transfer_probe.py" "$geogs_tp_out/"
cp -- "${BASH_SOURCE[0]}" "$geogs_tp_out/launcher.sh"
cat > "$geogs_tp_out/resource_deviation_before_probe.json" <<'JSON'
{
  "scientific_verdict": null,
  "purpose": "Measure pageable/pinned transfers before deciding whether another resource-only implementation is worthwhile",
  "training_processes_stopped_or_changed": false,
  "training_process_count": 2,
  "temporary_additional_gpu_process": 1,
  "resource_deviation": "The experiment's two-GPU-process limit is temporarily exceeded only by one bounded transfer probe; training remains unchanged. Concurrent timing is potentially perturbed.",
  "explicit_gpu_buffers_bytes": 67108864,
  "gpu_driver_context_excluded_from_buffer_cap": true,
  "explicit_host_buffers_bytes": 67108864,
  "transfer_scheduling_window_seconds": 8,
  "training_or_geometry_arithmetic": false,
  "inputs_or_reference_mounted": false
}
JSON
nvidia-smi --query-gpu=timestamp,index,uuid,memory.used,memory.free,utilization.gpu,pcie.link.gen.current,pcie.link.width.current --format=csv > "$geogs_tp_out/gpu_before.csv"
trap 'geogs_tp_exit=$?; printf "%s\n" "$geogs_tp_exit" > "$geogs_tp_out/exit_code.txt"' EXIT
docker run --rm --name jbgs-geogs-bounded-transfer-probe-v1 --network none --gpus device=0 \
  --cpus 1 --memory 512m --memory-swap 512m --user "$(id -u):$(id -g)" \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$geogs_tp_out,dst=/out" \
  "$geogs_tp_image" /opt/geogs/bin/python /out/transfer_probe.py \
  --device 0 --sizes-mib 2 8 32 --repeats 6 --max-gpu-seconds 8 \
  --receipt /out/transfer_probe.json > "$geogs_tp_out/stdout.log" 2> "$geogs_tp_out/stderr.log"
nvidia-smi --query-gpu=timestamp,index,uuid,memory.used,memory.free,utilization.gpu --format=csv > "$geogs_tp_out/gpu_after.csv"
cat "$geogs_tp_out/stdout.log"
