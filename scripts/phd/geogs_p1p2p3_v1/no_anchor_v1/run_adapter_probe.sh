#!/usr/bin/env bash
set -euo pipefail
geogs_ap_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd)
geogs_ap_task=$(realpath "$geogs_ap_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_ap_out="$geogs_ap_task/no_anchor_sfm_memory_recovery_v1/validation/adapter_probe_v1"
geogs_ap_code="$geogs_ap_repo/scripts/phd/geogs_p1p2p3_v1/no_anchor_v1"
geogs_ap_image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test ! -e "$geogs_ap_out"
mkdir -p -- "$geogs_ap_out"
cp -- "$geogs_ap_code/memory_recovery_v2/adapter_probe.py" "$geogs_ap_code/memory_recovery_v2/pinned_storage.py" "$geogs_ap_out/"
cp -- "$geogs_ap_task/no_anchor_sfm_memory_recovery_v1/source/jbgs_memory_recovery.py" "$geogs_ap_out/v1_adapter.py"
cp -- "${BASH_SOURCE[0]}" "$geogs_ap_out/launcher.sh"
cat > "$geogs_ap_out/resource_deviation_before_probe.json" <<'JSON'
{
  "scientific_verdict": null,
  "purpose": "Measure unchanged Adam state storage cycles before any decision to replace a running resource retry",
  "training_processes_stopped_or_changed": false,
  "training_process_count": 2,
  "temporary_additional_gpu_process": 1,
  "resource_deviation": "One short synthetic storage probe temporarily exceeds the planned two GPU processes; both training processes remain unchanged and their timing may be perturbed.",
  "gpu_allocator_cap_bytes": 134217728,
  "cuda_driver_context_excluded": true,
  "host_container_limit_bytes": 2147483648,
  "synthetic_points": 100000,
  "storage_scheduling_window_seconds": 8,
  "optimizer_steps_rendering_or_geometry": false,
  "training_inputs_or_reference_mounted": false,
  "restart_decision_threshold_before_measurement": "Consider a new pinned-memory retry only after exact state checks pass and median paired storage-cycle speed ratio v1/v2 is at least 2.0. This does not guarantee total-training speed."
}
JSON
nvidia-smi --query-gpu=timestamp,index,uuid,memory.used,memory.free,utilization.gpu --format=csv > "$geogs_ap_out/gpu_before.csv"
trap 'geogs_ap_exit=$?; printf "%s\n" "$geogs_ap_exit" > "$geogs_ap_out/exit_code.txt"' EXIT
docker run --rm --name jbgs-geogs-bounded-adapter-probe-v1 --network none --gpus device=0 \
  --cpus 1 --memory 2g --memory-swap 2g --user "$(id -u):$(id -g)" \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --mount "type=bind,src=$geogs_ap_out,dst=/out" \
  "$geogs_ap_image" /opt/geogs/bin/python /out/adapter_probe.py \
  --device 0 --points 100000 --repeats 4 --max-gpu-seconds 8 \
  --v1-adapter /out/v1_adapter.py --receipt /out/adapter_probe.json \
  > "$geogs_ap_out/stdout.log" 2> "$geogs_ap_out/stderr.log"
nvidia-smi --query-gpu=timestamp,index,uuid,memory.used,memory.free,utilization.gpu --format=csv > "$geogs_ap_out/gpu_after.csv"
cat "$geogs_ap_out/stdout.log"
