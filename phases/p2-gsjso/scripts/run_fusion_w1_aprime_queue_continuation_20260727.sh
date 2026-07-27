#!/usr/bin/env bash
# Docker-only, serial continuation of the 20 jobs remaining after smoke.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

CONFIG="phases/p2-gsjso/configs/fusion_w1_aprime_queue_continuation_20260727.json"
DRIVER="phases/p2-gsjso/scripts/fusion_w1_aprime_queue_continuation_20260727.py"
TEST="phases/p2-gsjso/scripts/test_fusion_w1_aprime_queue_continuation_20260727.py"
TRAINING_WRAPPER="phases/p2-gsjso/scripts/run_fusion_w1_aprime_training_20260726.sh"
READOUT_WRAPPER="phases/p2-gsjso/scripts/run_fusion_w1_aprime_readout_cachefix_20260727.sh"
QUEUE_ROOT="phases/p2-gsjso/runs/20260726_fusion_w1_aprime/unattended_queue_continuation_v2"
ACTION_LOG_ROOT="$QUEUE_ROOT/action_logs"
CONTROL_IMAGE="jointbuildgs:dev"
CONTROL_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
MEMORY_LIMIT="24g"
CPU_LIMIT="12"
GPU_INDEX="1"
GPU_BOUNDARY_POLL_SECONDS="30"
QUEUE_SHELL_PID="$$"
GPU_BOUNDARY_GUARDED_JOB_KEY=""
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

verify_control_image() {
  local observed
  observed="$(docker image inspect "$CONTROL_IMAGE" --format '{{.Id}}')"
  [[ "$observed" == "$CONTROL_IMAGE_ID" ]] || {
    echo "control image ID mismatch: $observed" >&2
    return 2
  }
}

run_tools() {
  docker run --rm \
    --pull=never \
    --network=none \
    --memory="$MEMORY_LIMIT" \
    --memory-swap="$MEMORY_LIMIT" \
    --cpus="$CPU_LIMIT" \
    --user "$HOST_UID:$HOST_GID" \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --volume "$REPO_ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$CONTROL_IMAGE" "$@"
}

acquire_queue_lock() {
  mkdir -p "$QUEUE_ROOT"
  exec 9>"$QUEUE_ROOT/driver.lock"
  if ! flock -n 9; then
    echo "A-prime continuation queue driver lock is already held" >&2
    exit 75
  fi
}

is_queue_owned_pid() {
  local cursor="$1"
  local parent=""
  while [[ "$cursor" =~ ^[1-9][0-9]*$ ]]; do
    if [[ "$cursor" == "$QUEUE_SHELL_PID" ]]; then
      return 0
    fi
    [[ "$cursor" -gt 1 && -r "/proc/$cursor/stat" ]] || return 1
    parent="$(ps -o ppid= -p "$cursor" 2>/dev/null || true)"
    parent="${parent//[[:space:]]/}"
    [[ "$parent" =~ ^[1-9][0-9]*$ && "$parent" != "$cursor" ]] || return 1
    cursor="$parent"
  done
  return 1
}

gpu1_unrelated_compute_rows() {
  local gpu_uuid=""
  local compute_rows=""
  local pid=""
  local process_name=""
  gpu_uuid="$(nvidia-smi --id="$GPU_INDEX" --query-gpu=uuid --format=csv,noheader,nounits)" || {
    echo "cannot query physical GPU $GPU_INDEX" >&2
    return 2
  }
  gpu_uuid="${gpu_uuid//[[:space:]]/}"
  [[ "$gpu_uuid" == GPU-* ]] || {
    echo "invalid UUID for physical GPU $GPU_INDEX: $gpu_uuid" >&2
    return 2
  }
  compute_rows="$(
    nvidia-smi --id="$GPU_INDEX" \
      --query-compute-apps=pid,process_name --format=csv,noheader,nounits
  )" || {
    echo "cannot query compute processes on physical GPU $GPU_INDEX" >&2
    return 2
  }
  while IFS=',' read -r pid process_name; do
    pid="${pid//[[:space:]]/}"
    [[ -n "$pid" ]] || continue
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || {
      echo "malformed GPU compute PID on physical GPU $GPU_INDEX: $pid" >&2
      return 2
    }
    # This is a secondary safety net.  Guards run only between synchronous
    # foreground actions, never while this queue's training/readout child is
    # running.
    if is_queue_owned_pid "$pid"; then
      continue
    fi
    printf '%s,%s\n' "$pid" "$process_name"
  done <<<"$compute_rows"
}

wait_for_gpu1_job_boundary() {
  local job_key="$1"
  local unrelated=""
  [[ "$GPU_BOUNDARY_POLL_SECONDS" =~ ^[1-9][0-9]*$ ]] || {
    echo "invalid GPU boundary poll interval: $GPU_BOUNDARY_POLL_SECONDS" >&2
    return 2
  }
  [[ "$GPU_BOUNDARY_POLL_SECONDS" -le 60 ]] || {
    echo "GPU boundary poll interval exceeds 60 seconds" >&2
    return 2
  }
  while true; do
    unrelated="$(gpu1_unrelated_compute_rows)" || return $?
    if [[ -z "$unrelated" ]]; then
      echo "GPU boundary ready: physical_gpu=$GPU_INDEX job=$job_key" >&2
      return 0
    fi
    echo "GPU boundary waiting: physical_gpu=$GPU_INDEX job=$job_key unrelated_compute=[$unrelated]" >&2
    sleep "$GPU_BOUNDARY_POLL_SECONDS"
  done
}

guard_job_and_cuda_action() {
  local action="$1"
  local building_id="$2"
  local arm="$3"
  local replicate="$4"
  local job_key=""
  local boundary_checked="false"
  case "$action" in
    STOP_STAGE|FINALIZE_QUEUE|DONE)
      return 0
      ;;
  esac
  job_key="$building_id|$arm|$replicate"
  if [[ "$job_key" != "$GPU_BOUNDARY_GUARDED_JOB_KEY" ]]; then
    wait_for_gpu1_job_boundary "$job_key|job_boundary"
    GPU_BOUNDARY_GUARDED_JOB_KEY="$job_key"
    boundary_checked="true"
  fi
  case "$action" in
    LAUNCH_TRAINING|RUN_READOUT)
      if [[ "$boundary_checked" != "true" ]]; then
        wait_for_gpu1_job_boundary "$job_key|before_$action"
      fi
      ;;
  esac
}

allocate_action_log() {
  local action="$1"
  local stage_key="$2"
  local stage_entry_order="$3"
  local building_id="$4"
  local arm="$5"
  local replicate="$6"
  local directory="$ACTION_LOG_ROOT/stage_${stage_key}/entry_$(printf '%02d' "$stage_entry_order")_${building_id}_arm_${arm}_${replicate}"
  local attempt=1
  local candidate
  mkdir -p "$directory"
  while true; do
    candidate="$directory/action_$(printf '%03d' "$attempt")_${action}.log"
    if (set -o noclobber; : >"$candidate") 2>/dev/null; then
      printf '%s\n' "$candidate"
      return 0
    fi
    attempt="$((attempt + 1))"
  done
}

record_action_failure() {
  local action="$1"
  local stage_key="$2"
  local stage_entry_order="$3"
  local status="$4"
  local log_path="$5"
  run_tools "$DRIVER" --config "$CONFIG" record-action-failure \
    --stage-key "$stage_key" --stage-entry-order "$stage_entry_order" \
    --action "$action" --error-type ExternalActionError \
    --message "external action exited nonzero" --return-code "$status" \
    --log-path "$log_path"
}

record_action_success() {
  local action="$1"
  local stage_key="$2"
  local stage_entry_order="$3"
  local log_path="$4"
  run_tools "$DRIVER" --config "$CONFIG" record-action-success \
    --stage-key "$stage_key" --stage-entry-order "$stage_entry_order" \
    --action "$action" --log-path "$log_path"
}

execute_action() {
  local action="$1"
  local stage_key="$2"
  local stage_entry_order="$3"
  local building_id="$4"
  local arm="$5"
  local replicate="$6"
  shift 6
  local log_path
  local status
  log_path="$(allocate_action_log "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate")"
  printf 'action=%s stage=%s entry=%s building=%s arm=%s replicate=%s\n' \
    "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" \
    >>"$log_path"
  set +e
  "$@" 2>&1 | tee -a "$log_path"
  status="${PIPESTATUS[0]}"
  set -e
  if [[ "$status" -eq 0 ]]; then
    record_action_success "$action" "$stage_key" "$stage_entry_order" "$log_path"
  else
    record_action_failure "$action" "$stage_key" "$stage_entry_order" "$status" "$log_path"
  fi
  return 0
}

launch_training_after_cache_check() {
  local building_id="$1"
  local arm="$2"
  local replicate="$3"
  # This probe uses the cachefix wrapper's locked jointbuildgs:dev image and
  # verifies non-root HOME/XDG/TORCH, exact prebuilt gsplat load, and an
  # unchanged reuse-only cache tree before training is allowed to start.
  env APRIME_READOUT_CACHEFIX_GPU_INDEX="$GPU_INDEX" \
    bash "$READOUT_WRAPPER" cache-check
  bash "$TRAINING_WRAPPER" launch \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --profile full --gpu "$GPU_INDEX"
}

run_queue() {
  local next_line
  local action stage_key stage_order stage_entry_order building_id arm replicate pipeline_state
  acquire_queue_lock
  run_tools "$DRIVER" --config "$CONFIG" verify
  run_tools "$DRIVER" --config "$CONFIG" initialize
  while true; do
    next_line="$(run_tools "$DRIVER" --config "$CONFIG" next --format tsv)"
    IFS=$'\t' read -r action stage_key stage_order stage_entry_order building_id arm replicate pipeline_state <<<"$next_line"
    guard_job_and_cuda_action "$action" "$building_id" "$arm" "$replicate"
    case "$action" in
      MATERIALIZE_TRAINING)
        execute_action "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" \
          bash "$TRAINING_WRAPPER" materialize \
            --building-id "$building_id" --arm "$arm" --run "$replicate" --profile full
        ;;
      LAUNCH_TRAINING)
        execute_action "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" \
          launch_training_after_cache_check "$building_id" "$arm" "$replicate"
        ;;
      RUN_READOUT)
        execute_action "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" \
          env APRIME_READOUT_CACHEFIX_GPU_INDEX="$GPU_INDEX" \
          bash "$READOUT_WRAPPER" one "$building_id" "$arm" "$replicate"
        ;;
      ARCHIVE_TRAINING)
        execute_action "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" \
          run_tools "$DRIVER" --config "$CONFIG" archive-training \
            --stage-key "$stage_key" --stage-entry-order "$stage_entry_order"
        ;;
      RECORD_MEASURED|RECORD_SKIPPED)
        run_tools "$DRIVER" --config "$CONFIG" record-terminal \
          --stage-key "$stage_key" --stage-entry-order "$stage_entry_order"
        ;;
      WAIT_TRAINING|WAIT_READOUT)
        sleep 5
        ;;
      STOP_STAGE)
        run_tools "$DRIVER" --config "$CONFIG" stop-stage
        ;;
      FINALIZE_QUEUE)
        run_tools "$DRIVER" --config "$CONFIG" finalize
        return 0
        ;;
      DONE)
        return 0
        ;;
      *)
        echo "unknown queue action: $action (state=$pipeline_state stage_order=$stage_order)" >&2
        return 2
        ;;
    esac
  done
}

verify_control_image

case "${1:-}" in
  test)
    run_tools -m unittest -v "$TEST"
    ;;
  verify)
    run_tools "$DRIVER" --config "$CONFIG" verify
    ;;
  run)
    run_queue
    ;;
  snapshot)
    run_tools "$DRIVER" --config "$CONFIG" snapshot
    ;;
  next)
    run_tools "$DRIVER" --config "$CONFIG" next --format json
    ;;
  *)
    echo "usage: $0 {test|verify|run|snapshot|next}" >&2
    exit 2
    ;;
esac
