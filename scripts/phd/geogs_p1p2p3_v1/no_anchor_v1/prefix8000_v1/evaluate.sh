#!/usr/bin/env bash
# Explicit single-stage execution only. No training, export or evaluation loop.
set -euo pipefail
prefix_ev_region=${1:?P1 P2 P3}
prefix_ev_stage=${2:?seal geometry renders summary}
case "$prefix_ev_region" in P1) prefix_ev_attempt=no_anchor_sfm_memory_recovery_v2 ;; P2) prefix_ev_attempt=no_anchor_sfm_memory_recovery_P2_v2 ;; P3) prefix_ev_attempt=no_anchor_sfm_memory_recovery_P3_v3 ;; *) exit 2 ;; esac
case "$prefix_ev_stage" in seal|geometry|renders|summary) ;; *) exit 2 ;; esac
prefix_ev_cpus=2
prefix_ev_memory_gib=3
prefix_ev_shm=256m
prefix_ev_heavy_lock=false
case "$prefix_ev_stage" in
  geometry) prefix_ev_cpus=8; prefix_ev_memory_gib=32; prefix_ev_shm=4g; prefix_ev_heavy_lock=true ;;
  renders) prefix_ev_cpus=4; prefix_ev_memory_gib=8 ;;
esac
prefix_ev_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../../.." && pwd)
prefix_ev_artifacts=$(realpath "$prefix_ev_repo/../JointBuildGS-artifacts")
prefix_ev_task="$prefix_ev_artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
prefix_ev_root="$prefix_ev_task/evaluation/no_anchor_sfm_prefix8000_v1"
prefix_ev_log="$prefix_ev_root/execution/$prefix_ev_region/R8000/$prefix_ev_stage"
test -f "$prefix_ev_task/completed_prefix8000_v1/$prefix_ev_region/validation/receipt.json"
test -f "$prefix_ev_task/completed_prefix8000_v1/$prefix_ev_region/export/receipt.json"
test ! -e "$prefix_ev_log"
mkdir -p "$prefix_ev_log/code"
cp -- "${BASH_SOURCE[0]}" "$prefix_ev_log/launcher_snapshot.sh"
cp -- "$(dirname -- "${BASH_SOURCE[0]}")/evaluate.py" "$prefix_ev_log/code/evaluate_prefix.py"
cp -- "$(dirname -- "${BASH_SOURCE[0]}")/../evaluate.py" "$prefix_ev_log/code/evaluate_core.py"
cp -- "$prefix_ev_task/contracts/sfm_prefix8000_diagnostic_v1.json" "$prefix_ev_log/policy_snapshot.json"
cat > "$prefix_ev_log/resource_plan.json" <<EOF
{
  "schema": "GEOGS_PREFIX_EVALUATION_RESOURCES_v1",
  "scientific_verdict": null,
  "region": "$prefix_ev_region",
  "stage": "$prefix_ev_stage",
  "optimizer_updates": 8000,
  "cpus": $prefix_ev_cpus,
  "memory_limit_bytes": $((prefix_ev_memory_gib * 1024 * 1024 * 1024)),
  "memory_swap_limit_equals_ram": true,
  "shm_size": "$prefix_ev_shm",
  "gpu_devices_requested": false,
  "metric_device": "cpu",
  "shared_heavy_cpu_lock": $prefix_ev_heavy_lock,
  "shared_lock_task_relative": "no_anchor_sfm_v1/locks/heavy_cpu.lock",
  "score_math_changed": false,
  "cpu_gpu_bitwise_metric_equality_claimed": false,
  "resource_choice_basis": "Fixed before actual prefix quality evaluation; geometry matches main evaluation 8CPU/32GiB, CPU metric scoring uses 4CPU/8GiB, seal and summary use 2CPU/3GiB.",
  "timing_scope": "Docker launch through evaluator exit, excluding shared-lock waiting; includes container startup and validation.",
  "render_timing_comparison": "The renders stage scores already exported RGB on CPU. Its duration is not a GPU scoring, Gaussian rendering, TSDF extraction or training duration; do not compare it directly with earlier GPU scoring times."
}
EOF
prefix_ev_extra=()
if [[ "$prefix_ev_stage" == geometry ]]; then
  prefix_ev_ref="$prefix_ev_artifacts/phase-payloads/phd/wu_vallet_regions_v4/PHD-WU-VALLET-REGIONS-EVALUATION-v4/run/$prefix_ev_region/reference.npz"
  prefix_ev_extra+=(--mount "type=bind,src=$prefix_ev_ref,dst=/reference/$prefix_ev_region/reference.npz,readonly")
fi
prefix_ev_cmd=(docker run --rm --read-only --network none --cpus "$prefix_ev_cpus" --memory "${prefix_ev_memory_gib}g" --memory-swap "${prefix_ev_memory_gib}g" --pids-limit 256
  --user "$(id -u):$(id -g)" --tmpfs /tmp:rw,nosuid,size=512m --shm-size "$prefix_ev_shm"
  --env PYTHONDONTWRITEBYTECODE=1 --env "OMP_NUM_THREADS=$prefix_ev_cpus" --env "OPENBLAS_NUM_THREADS=$prefix_ev_cpus"
  --env NVIDIA_VISIBLE_DEVICES=void
  --env MPLCONFIGDIR=/tmp/mpl --env TORCH_HOME=/weights/torch --env LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6
  --mount "type=bind,src=$prefix_ev_task,dst=/task,readonly"
  --mount "type=bind,src=$prefix_ev_root,dst=/out"
  --mount "type=bind,src=$prefix_ev_repo/scripts/phd/geogs_p1p2p3_v1,dst=/audit,readonly"
  --mount "type=bind,src=$prefix_ev_task/sources/GeoGS-state-camera-v1,dst=/source,readonly"
  --mount "type=bind,src=$prefix_ev_task/runtime/weights,dst=/weights,readonly"
  "${prefix_ev_extra[@]}" sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
  python "/out/execution/$prefix_ev_region/R8000/$prefix_ev_stage/code/evaluate_prefix.py"
  --task /task --experiment "/task/$prefix_ev_attempt" --out /out --region "$prefix_ev_region" --stage "$prefix_ev_stage"
  --evaluation-lib /audit/evaluation --core-evaluator "/out/execution/$prefix_ev_region/R8000/$prefix_ev_stage/code/evaluate_core.py" --device cpu)
printf '%q ' "${prefix_ev_cmd[@]}" > "$prefix_ev_log/command.sh"
printf '\n' >> "$prefix_ev_log/command.sh"
prefix_ev_wait_started=$(date +%s.%N)
if [[ "$prefix_ev_heavy_lock" == true ]]; then
  mkdir -p "$prefix_ev_task/no_anchor_sfm_v1/locks"
  exec {prefix_ev_lock_fd}> "$prefix_ev_task/no_anchor_sfm_v1/locks/heavy_cpu.lock"
  printf '%s\n' WAITING_FOR_SHARED_HEAVY_CPU_LOCK > "$prefix_ev_log/status.txt"
  flock "$prefix_ev_lock_fd"
fi
prefix_ev_started=$(date +%s.%N)
printf '%s\n' EVALUATOR_RUNNING > "$prefix_ev_log/status.txt"
set +e
"${prefix_ev_cmd[@]}" > "$prefix_ev_log/stdout.log" 2> "$prefix_ev_log/stderr.log"
prefix_ev_exit=$?
set -e
prefix_ev_finished=$(date +%s.%N)
if [[ "$prefix_ev_heavy_lock" == true ]]; then
  flock -u "$prefix_ev_lock_fd"
  exec {prefix_ev_lock_fd}>&-
fi
prefix_ev_wait_seconds=$(awk -v began="$prefix_ev_wait_started" -v started="$prefix_ev_started" 'BEGIN {printf "%.6f", started-began}')
prefix_ev_work_seconds=$(awk -v started="$prefix_ev_started" -v finished="$prefix_ev_finished" 'BEGIN {printf "%.6f", finished-started}')
cat > "$prefix_ev_log/resource_receipt.json" <<EOF
{
  "schema": "GEOGS_PREFIX_EVALUATION_RESOURCE_RECEIPT_v1",
  "scientific_verdict": null,
  "region": "$prefix_ev_region",
  "stage": "$prefix_ev_stage",
  "evaluator_exit_code": $prefix_ev_exit,
  "shared_lock_wait_started_unix": $prefix_ev_wait_started,
  "docker_started_unix": $prefix_ev_started,
  "docker_finished_unix": $prefix_ev_finished,
  "shared_lock_wait_seconds": $prefix_ev_wait_seconds,
  "docker_phase_wall_seconds": $prefix_ev_work_seconds,
  "resource_plan_file": "resource_plan.json",
  "metric_device": "cpu",
  "gpu_devices_requested": false,
  "quality_status_inferred_from_resource_receipt": false,
  "direct_comparison_to_gpu_scoring_time_allowed": false
}
EOF
printf '%s\n' EVALUATOR_EXITED > "$prefix_ev_log/status.txt"
printf '%s\n' "$prefix_ev_exit" > "$prefix_ev_log/exit_code.txt"
(cd "$prefix_ev_log" && rg --files -0 -g '!SHA256SUMS' | sort -z | xargs -0 sha256sum) > "$prefix_ev_log/SHA256SUMS"
cat "$prefix_ev_log/stdout.log" "$prefix_ev_log/stderr.log"
exit "$prefix_ev_exit"
