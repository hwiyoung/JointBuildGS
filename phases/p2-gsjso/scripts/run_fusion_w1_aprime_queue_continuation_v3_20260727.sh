#!/usr/bin/env bash
# Two training lanes followed by globally serial quantitative/qualitative readout.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

CONFIG="phases/p2-gsjso/configs/fusion_w1_aprime_queue_continuation_v3_20260727.json"
DRIVER="phases/p2-gsjso/scripts/fusion_w1_aprime_queue_continuation_v3_20260727.py"
TEST="phases/p2-gsjso/scripts/test_fusion_w1_aprime_queue_continuation_v3_20260727.py"
TRAINING_WRAPPER="phases/p2-gsjso/scripts/run_fusion_w1_aprime_training_20260726.sh"
READOUT_WRAPPER="phases/p2-gsjso/scripts/run_fusion_w1_aprime_readout_cachefix_20260727.sh"
QUALITATIVE_WRAPPER="phases/p2-gsjso/scripts/run_fusion_w1_aprime_job_qualitative_v3_20260727.sh"
QUEUE_ROOT="phases/p2-gsjso/runs/20260726_fusion_w1_aprime/unattended_queue_continuation_v3_repair1"
ACTION_LOG_ROOT="$QUEUE_ROOT/action_logs"
READOUT_LOCK="$QUEUE_ROOT/locks/readout_global.lock"
SERVICE_LOG="$QUEUE_ROOT/service.log"
CONTROL_IMAGE="jointbuildgs:dev"
CONTROL_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
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
  docker run --rm --pull=never --network=none --memory=24g --memory-swap=24g --cpus=12 \
    --user "$HOST_UID:$HOST_GID" --env PYTHONDONTWRITEBYTECODE=1 \
    --volume "$REPO_ROOT:/workspace/JointBuildGS" --workdir /workspace/JointBuildGS \
    --entrypoint python3 "$CONTROL_IMAGE" "$@"
}

acquire_driver_lock() {
  mkdir -p "$QUEUE_ROOT"
  exec 9>"$QUEUE_ROOT/driver.lock"
  if ! flock -n 9; then
    echo "v3 continuation driver lock is already held" >&2
    exit 75
  fi
}

start_service_log() {
  mkdir -p "$QUEUE_ROOT"
  if [[ -n "${INVOCATION_ID:-}" ]]; then
    # systemd StandardOutput/StandardError owns the append to SERVICE_LOG.
    exec > >(stdbuf -oL awk '{ print strftime("%Y-%m-%dT%H:%M:%S%z"), $0; fflush(); }') 2>&1
  else
    exec > >(stdbuf -oL awk '{ print strftime("%Y-%m-%dT%H:%M:%S%z"), $0; fflush(); }' | stdbuf -oL tee -a "$SERVICE_LOG") 2>&1
  fi
}

allocate_action_log() {
  local action="$1" stage_key="$2" stage_entry_order="$3" building_id="$4" arm="$5" replicate="$6"
  local directory="$ACTION_LOG_ROOT/stage_${stage_key}/entry_$(printf '%02d' "$stage_entry_order")_${building_id}_arm_${arm}_${replicate}"
  local attempt=1 candidate
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

normalize_action_diagnostic() {
  local log_path="$1" diagnostic
  diagnostic="$(awk '
    BEGIN { preferred=""; fallback="" }
    NF { fallback=$0 }
    /ERROR:|Error|error|FAILED|failed|mismatch|refus/ { preferred=$0 }
    END { if (preferred != "") print preferred; else print fallback }
  ' "$log_path" | tr '\t' ' ' | tr -cd '[:print:]' | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//' | cut -c1-512)"
  [[ -n "$diagnostic" ]] || diagnostic="no diagnostic text"
  printf '%s\n' "$diagnostic"
}

record_failure() {
  local action="$1" stage_key="$2" stage_entry_order="$3" status="$4" log_path="$5"
  local invocation_id diagnostic
  invocation_id="${stage_key}.${stage_entry_order}.${action}.$(basename "$log_path" .log)"
  diagnostic="$(normalize_action_diagnostic "$log_path")"
  run_tools "$DRIVER" --config "$CONFIG" record-action-failure \
    --stage-key "$stage_key" --stage-entry-order "$stage_entry_order" \
    --invocation-id "$invocation_id" --action "$action" \
    --error-type "${action}ExternalError" --message "external action diagnostic: $diagnostic" \
    --return-code "$status" --log-path "$log_path"
}

execute_action() {
  local action="$1" stage_key="$2" stage_entry_order="$3" building_id="$4" arm="$5" replicate="$6"
  shift 6
  local log_path status
  log_path="$(allocate_action_log "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate")"
  printf 'action=%s stage=%s entry=%s building=%s arm=%s replicate=%s\n' \
    "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" >>"$log_path"
  set +e
  "$@" 2>&1 | tee -a "$log_path"
  status="${PIPESTATUS[0]}"
  set -e
  if [[ "$status" -ne 0 ]]; then
    record_failure "$action" "$stage_key" "$stage_entry_order" "$status" "$log_path"
  fi
  return 0
}

inspect_tsv() {
  run_tools "$DRIVER" --config "$CONFIG" inspect \
    --stage-key "$1" --stage-entry-order "$2" --format tsv
}

launch_lane() {
  local pair_id="$1" gpu="$2" stage_key="$3" stage_entry_order="$4"
  /usr/bin/python3 "$DRIVER" --config "$CONFIG" wait-gpu-boundary --pair-id "$pair_id" --gpu "$gpu"
  /usr/bin/python3 "$DRIVER" --config "$CONFIG" launch-training \
    --stage-key "$stage_key" --stage-entry-order "$stage_entry_order" --gpu "$gpu"
}

drive_training_member() {
  local pair_id="$1" gpu="$2" stage_key="$3" stage_entry_order="$4" building_id="$5" arm="$6" replicate="$7"
  local line state action
  while true; do
    line="$(inspect_tsv "$stage_key" "$stage_entry_order")"
    IFS=$'\t' read -r state action <<<"$line"
    case "$action" in
      MATERIALIZE_TRAINING)
        execute_action "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" \
          bash "$TRAINING_WRAPPER" materialize --building-id "$building_id" --arm "$arm" --run "$replicate" --profile full
        ;;
      LAUNCH_TRAINING)
        execute_action "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" \
          launch_lane "$pair_id" "$gpu" "$stage_key" "$stage_entry_order"
        ;;
      ARCHIVE_TRAINING)
        execute_action "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" \
          run_tools "$DRIVER" --config "$CONFIG" archive-training --stage-key "$stage_key" --stage-entry-order "$stage_entry_order"
        ;;
      WAIT_TRAINING)
        sleep 30
        ;;
      RECORD_TERMINAL)
        run_tools "$DRIVER" --config "$CONFIG" record-terminal --stage-key "$stage_key" --stage-entry-order "$stage_entry_order"
        return 0
        ;;
      RUN_READOUT|RUN_QUALITATIVE|NONE)
        return 0
        ;;
      *)
        echo "unsupported training-lane action=$action state=$state job=$building_id/$arm/$replicate" >&2
        return 2
        ;;
    esac
  done
}

drive_post_training_member() {
  local stage_key="$1" stage_entry_order="$2" building_id="$3" arm="$4" replicate="$5"
  local line state action
  while true; do
    line="$(inspect_tsv "$stage_key" "$stage_entry_order")"
    IFS=$'\t' read -r state action <<<"$line"
    case "$action" in
      RUN_READOUT)
        /usr/bin/python3 "$DRIVER" --config "$CONFIG" assert-no-training
        execute_action "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" \
          flock "$READOUT_LOCK" env APRIME_READOUT_CACHEFIX_GPU_INDEX=1 \
            bash "$READOUT_WRAPPER" one "$building_id" "$arm" "$replicate"
        ;;
      RUN_QUALITATIVE)
        /usr/bin/python3 "$DRIVER" --config "$CONFIG" assert-no-training
        execute_action "$action" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" \
          bash "$QUALITATIVE_WRAPPER" one "$building_id" "$arm" "$replicate"
        ;;
      RECORD_TERMINAL)
        run_tools "$DRIVER" --config "$CONFIG" record-terminal --stage-key "$stage_key" --stage-entry-order "$stage_entry_order"
        return 0
        ;;
      NONE)
        return 0
        ;;
      WAIT_READOUT)
        sleep 30
        ;;
      *)
        echo "unsupported post-training action=$action state=$state job=$building_id/$arm/$replicate" >&2
        return 2
        ;;
    esac
  done
}

bootstrap_reused_source() {
  drive_post_training_member "aprime_r1" 2 "DEBY_LOD2_42364659" "Aprime" "r1"
  run_tools "$DRIVER" --config "$CONFIG" stage-stop-check
}

load_pair_schedule() {
  local target_name="$1" pair_tsv producer_status row
  local pair_order pair_id stage_order stage_key member_order gpu stage_entry_order building_id arm replicate
  local -n target_rows="$target_name"
  local -A unique_pair_ids=()
  if pair_tsv="$(run_tools "$DRIVER" --config "$CONFIG" pairs --format tsv)"; then
    :
  else
    producer_status="$?"
    echo "pair schedule producer failed with status=$producer_status" >&2
    return "$producer_status"
  fi
  mapfile -t target_rows <<<"$pair_tsv"
  if [[ "${#target_rows[@]}" -ne 19 ]]; then
    echo "pair schedule row count mismatch: expected=19 observed=${#target_rows[@]}" >&2
    return 2
  fi
  for row in "${target_rows[@]}"; do
    IFS=$'\t' read -r pair_order pair_id stage_order stage_key member_order gpu stage_entry_order building_id arm replicate <<<"$row"
    if [[ -z "$pair_id" || -z "$building_id" || -z "$arm" || -z "$replicate" ]]; then
      echo "pair schedule contains a malformed row" >&2
      return 2
    fi
    unique_pair_ids["$pair_id"]=1
  done
  if [[ "${#unique_pair_ids[@]}" -ne 11 ]]; then
    echo "pair schedule unique pair count mismatch: expected=11 observed=${#unique_pair_ids[@]}" >&2
    return 2
  fi
}

wait_for_training_pair() {
  local pid child_status first_failure=0
  local -a observed_statuses=()
  for pid in "$@"; do
    if wait "$pid"; then
      child_status=0
    else
      child_status="$?"
    fi
    observed_statuses+=("$pid:$child_status")
    if [[ "$child_status" -ne 0 && "$first_failure" -eq 0 ]]; then
      first_failure="$child_status"
    fi
  done
  printf 'training pair children reaped statuses=%s\n' "$(IFS=,; printf '%s' "${observed_statuses[*]}")"
  return "$first_failure"
}

run_queue() {
  local -a pair_rows current_rows pids
  local row pair_order pair_id stage_order stage_key member_order gpu stage_entry_order building_id arm replicate current_pair=""
  acquire_driver_lock
  mkdir -p "$QUEUE_ROOT/locks"
  start_service_log
  verify_control_image
  run_tools "$DRIVER" --config "$CONFIG" verify
  run_tools "$DRIVER" --config "$CONFIG" initialize
  if [[ -f "$QUEUE_ROOT/complete.json" ]]; then
    run_tools "$DRIVER" --config "$CONFIG" finalize
    return 0
  fi
  bootstrap_reused_source
  load_pair_schedule pair_rows
  for row in "${pair_rows[@]}"; do
    IFS=$'\t' read -r pair_order pair_id stage_order stage_key member_order gpu stage_entry_order building_id arm replicate <<<"$row"
    [[ "$pair_id" != "$current_pair" ]] || continue
    current_pair="$pair_id"
    [[ ! -f "$QUEUE_ROOT/stage_stop.json" ]] || break
    current_rows=()
    for row in "${pair_rows[@]}"; do
      IFS=$'\t' read -r pair_order pair_id stage_order stage_key member_order gpu stage_entry_order building_id arm replicate <<<"$row"
      [[ "$pair_id" == "$current_pair" ]] && current_rows+=("$row")
    done
    pids=()
    for row in "${current_rows[@]}"; do
      IFS=$'\t' read -r pair_order pair_id stage_order stage_key member_order gpu stage_entry_order building_id arm replicate <<<"$row"
      drive_training_member "$pair_id" "$gpu" "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate" &
      pids+=("$!")
    done
    wait_for_training_pair "${pids[@]}"
    run_tools "$DRIVER" --config "$CONFIG" pair-training-ready --pair-id "$current_pair"
    /usr/bin/python3 "$DRIVER" --config "$CONFIG" assert-no-training
    run_tools "$DRIVER" --config "$CONFIG" stage-stop-check
    if [[ -f "$QUEUE_ROOT/stage_stop.json" ]]; then
      run_tools "$DRIVER" --config "$CONFIG" status
      break
    fi
    for row in "${current_rows[@]}"; do
      IFS=$'\t' read -r pair_order pair_id stage_order stage_key member_order gpu stage_entry_order building_id arm replicate <<<"$row"
      drive_post_training_member "$stage_key" "$stage_entry_order" "$building_id" "$arm" "$replicate"
      run_tools "$DRIVER" --config "$CONFIG" stage-stop-check
      [[ ! -f "$QUEUE_ROOT/stage_stop.json" ]] || break
    done
    run_tools "$DRIVER" --config "$CONFIG" status
  done
  run_tools "$DRIVER" --config "$CONFIG" finalize
}

mode="${1:-}"
case "$mode" in
  test)
    verify_control_image
    run_tools "$TEST"
    ;;
  verify)
    verify_control_image
    run_tools "$DRIVER" --config "$CONFIG" verify
    ;;
  initialize)
    verify_control_image
    run_tools "$DRIVER" --config "$CONFIG" initialize
    ;;
  status)
    verify_control_image
    run_tools "$DRIVER" --config "$CONFIG" status
    ;;
  run)
    run_queue
    ;;
  *)
    echo "usage: $0 {test|verify|initialize|status|run}" >&2
    exit 64
    ;;
esac
