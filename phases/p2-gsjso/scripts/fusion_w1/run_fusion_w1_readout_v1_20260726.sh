#!/usr/bin/env bash
# Fusion W1 §5 serial pointcloud -> classify -> Roofer -> score wrapper.
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CONFIG="phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_v1_20260726.json"
RETRY_POLICY="phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_infra_retry_20260726.json"
RECOVERY2_POLICY="phases/p2-gsjso/configs/fusion_w1/fusion_w1_readout_infra_retry2_20260726.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1/fusion_w1_readout_v1_20260726.py"
TEST="tests/fusion_w1/test_fusion_w1_readout_v1_20260726.py"
RUN_REL="phases/p2-gsjso/runs/fusion_w1/20260724_fusion_w1"
READOUT_REL="$RUN_REL/readout_v1"

READOUT_IMAGE="jointbuildgs:dev"
READOUT_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
TOOLS_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
MEMORY_LIMIT="24g"
ROOFER_TIMEOUT_SECONDS=900
CATASTROPHE_STOP_N=3

run_tools() {
  docker run --rm \
    --pull=never \
    --network=none \
    --memory="$MEMORY_LIMIT" \
    --memory-swap="$MEMORY_LIMIT" \
    --shm-size=4g \
    --user "$(id -u):$(id -g)" \
    --env MPLCONFIGDIR=/tmp/fusion-w1-matplotlib \
    --env XDG_CACHE_HOME=/tmp/fusion-w1-cache \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --volume "$ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$TOOLS_IMAGE" "$@"
}

verify_tools_image() {
  local observed
  observed="$(docker image inspect "$TOOLS_IMAGE" --format '{{.Id}}')"
  [[ "$observed" == "$TOOLS_IMAGE_ID" ]] || {
    echo "tools image ID mismatch: $observed" >&2
    return 2
  }
}

verify_images() {
  local observed
  verify_tools_image
  observed="$(docker image inspect "$READOUT_IMAGE" --format '{{.Id}}')"
  [[ "$observed" == "$READOUT_IMAGE_ID" ]] || {
    echo "readout image ID mismatch: $observed" >&2
    return 2
  }
  docker image inspect "$ROOFER_IMAGE" >/dev/null
}

validate_gpu() {
  [[ "$1" == "0" || "$1" == "1" ]] || {
    echo "physical GPU must be 0 or 1" >&2
    return 2
  }
}

assert_no_training_or_other_readout() {
  local host_pattern docker_pattern
  host_pattern='src[.]stage2[.]train|fusion_w1_training_v1_20260725[.]py|run_fusion_w1_training_v1_20260725[.]sh|fusion_w1_seed_p0prime_20260725[.]py|pilot_1wave_postprocess_driver|run_primary4_assembly_validation|tum_mob_tsdf_extract[.]py|_mob_prep_las[.]py'
  docker_pattern='jointbuildgs-fusw1|src[.]stage2[.]train|tum_mob_tsdf_extract[.]py|_mob_prep_las[.]py|3dgi/roofer'
  if ps -eo pid=,args= | grep -E "$host_pattern" | grep -v -E 'grep -E|run_fusion_w1_readout_v1_20260726[.]sh' >/dev/null; then
    echo "training/other-readout host process guard matched" >&2
    ps -eo pid=,args= | grep -E "$host_pattern" | grep -v -E 'grep -E|run_fusion_w1_readout_v1_20260726[.]sh' >&2 || true
    return 75
  fi
  if docker ps --format '{{.ID}} {{.Image}} {{.Command}} {{.Names}}' \
      | grep -E "$docker_pattern" >/dev/null; then
    echo "training/other-readout Docker process guard matched" >&2
    docker ps --format '{{.ID}} {{.Image}} {{.Command}} {{.Names}}' \
      | grep -E "$docker_pattern" >&2 || true
    return 75
  fi
}

acquire_serial_lock() {
  mkdir -p "$READOUT_REL"
  exec 9>"$READOUT_REL/driver.lock"
  if ! flock -n 9; then
    echo "Fusion W1 readout serial lock is already held" >&2
    exit 75
  fi
  # The training launcher takes this lock before it can start Docker. Holding
  # it closes the check-to-launch race after the process guard below.
  mkdir -p "$RUN_REL/training"
  exec 8>"$RUN_REL/training/runtime_counters.json.lock"
  if ! flock -n 8; then
    echo "Fusion W1 training launch barrier is busy" >&2
    exit 75
  fi
}

record_external_failure() {
  local building_id="$1"
  local arm="$2"
  local run="$3"
  local stage="$4"
  local message="$5"
  run_tools "$SCRIPT" --config "$CONFIG" record-failure \
    --building-id "$building_id" \
    --arm "$arm" \
    --run "$run" \
    --stage "$stage" \
    --message "$message" || true
}

run_one() {
  local building_id="$1"
  local arm="$2"
  local run="$3"
  local gpu="$4"
  local mode="${5:-full}"
  local job_rel="$READOUT_REL/by_building/$building_id/arm_$arm/$run"
  local started ended wall
  local argv_text environment_text
  local -a argv
  local -a environment_args

  if [[ "$mode" != "post-extract" ]]; then
  assert_no_training_or_other_readout || return $?
  run_tools "$SCRIPT" --config "$CONFIG" prepare-one \
    --building-id "$building_id" --arm "$arm" --run "$run" || return $?

  assert_no_training_or_other_readout || return $?
  run_tools "$SCRIPT" --config "$CONFIG" authorize-extract \
    --building-id "$building_id" --arm "$arm" --run "$run" || return $?
  if ! argv_text="$(
      run_tools "$SCRIPT" --config "$CONFIG" extract-argv \
        --building-id "$building_id" --arm "$arm" --run "$run"
    )"
  then
    record_external_failure "$building_id" "$arm" "$run" "readout_argv" \
      "failed to resolve the immutable readout argv"
    return 1
  fi
  mapfile -t argv < <(printf '%s\n' "$argv_text")
  [[ "${#argv[@]}" -gt 1 ]] || {
    record_external_failure "$building_id" "$arm" "$run" "readout_argv" \
      "readout argv is empty"
    return 1
  }
  if ! environment_text="$(
      run_tools "$SCRIPT" --config "$CONFIG" extract-environment \
        --building-id "$building_id" --arm "$arm" --run "$run"
    )"
  then
    record_external_failure "$building_id" "$arm" "$run" "readout_environment" \
      "failed to resolve the immutable readout environment"
    return 1
  fi
  environment_args=()
  while IFS= read -r value; do
    [[ -n "$value" ]] && environment_args+=(--env "$value")
  done < <(printf '%s\n' "$environment_text")
  [[ "${#environment_args[@]}" -eq 8 ]] || {
    record_external_failure "$building_id" "$arm" "$run" "readout_environment" \
      "readout environment does not contain the three cache variables plus MAX_JOBS=1"
    return 1
  }
  started="$(date +%s)"
  if ! docker run --rm \
      --pull=never \
      --network=none \
      --memory="$MEMORY_LIMIT" \
      --memory-swap="$MEMORY_LIMIT" \
      --shm-size=4g \
      --gpus "device=$gpu" \
      --user "$(id -u):$(id -g)" \
      --env CUDA_VISIBLE_DEVICES=0 \
      --env PYTHONDONTWRITEBYTECODE=1 \
      "${environment_args[@]}" \
      --volume "$ROOT:/workspace/JointBuildGS" \
      --workdir /workspace/JointBuildGS \
      --entrypoint python3 \
      "$READOUT_IMAGE" "${argv[@]}" \
      >"$job_rel/extract.stdout.log" 2>&1
  then
    record_external_failure "$building_id" "$arm" "$run" "readout" \
      "point-cloud readout failed; see $job_rel/extract.stdout.log"
    return 1
  fi
  ended="$(date +%s)"
  wall="$((ended - started))"
  run_tools "$SCRIPT" --config "$CONFIG" accept-extract \
    --building-id "$building_id" --arm "$arm" --run "$run" \
    --wall-seconds "$wall" || return $?
  fi

  assert_no_training_or_other_readout || return $?
  run_tools "$SCRIPT" --config "$CONFIG" authorize-classification \
    --building-id "$building_id" --arm "$arm" --run "$run" || return $?
  if ! argv_text="$(
      run_tools "$SCRIPT" --config "$CONFIG" classification-argv \
        --building-id "$building_id" --arm "$arm" --run "$run"
    )"
  then
    record_external_failure "$building_id" "$arm" "$run" "classification_argv" \
      "failed to resolve the immutable classification argv"
    return 1
  fi
  mapfile -t argv < <(printf '%s\n' "$argv_text")
  [[ "${#argv[@]}" -gt 1 ]] || {
    record_external_failure "$building_id" "$arm" "$run" "classification_argv" \
      "classification argv is empty"
    return 1
  }
  started="$(date +%s)"
  if ! run_tools "${argv[@]}" >"$job_rel/classification.stdout.log" 2>&1; then
    record_external_failure "$building_id" "$arm" "$run" "classification" \
      "classification failed; see $job_rel/classification.stdout.log"
    return 1
  fi
  ended="$(date +%s)"
  wall="$((ended - started))"
  run_tools "$SCRIPT" --config "$CONFIG" accept-classification \
    --building-id "$building_id" --arm "$arm" --run "$run" \
    --wall-seconds "$wall" || return $?

  assert_no_training_or_other_readout || return $?
  run_tools "$SCRIPT" --config "$CONFIG" authorize-roofer \
    --building-id "$building_id" --arm "$arm" --run "$run" || return $?
  if ! argv_text="$(
      run_tools "$SCRIPT" --config "$CONFIG" roofer-argv \
        --building-id "$building_id" --arm "$arm" --run "$run"
    )"
  then
    record_external_failure "$building_id" "$arm" "$run" "roofer_path_resolution" \
      "failed to resolve the immutable Roofer argv"
    return 1
  fi
  mapfile -t argv < <(printf '%s\n' "$argv_text")
  if [[ "${#argv[@]}" -lt 4 ]]; then
    record_external_failure "$building_id" "$arm" "$run" "roofer_path_resolution" \
      "Roofer argv is incomplete"
    return 1
  fi
  started="$(date +%s)"
  if ! timeout --signal=TERM --kill-after=30s "$ROOFER_TIMEOUT_SECONDS" \
    docker run --rm \
      --pull=never \
      --network=none \
      --memory="$MEMORY_LIMIT" \
      --memory-swap="$MEMORY_LIMIT" \
      --user "$(id -u):$(id -g)" \
      --volume "$ROOT:/workspace/JointBuildGS" \
      --workdir /workspace/JointBuildGS \
      "$ROOFER_IMAGE" \
      "${argv[@]}" \
      >"$job_rel/roofer.stdout.log" 2>&1
  then
    record_external_failure "$building_id" "$arm" "$run" "roofer" \
      "Roofer failed or timed out; see $job_rel/roofer.stdout.log"
    return 1
  fi
  ended="$(date +%s)"
  wall="$((ended - started))"
  run_tools "$SCRIPT" --config "$CONFIG" accept-roofer \
    --building-id "$building_id" --arm "$arm" --run "$run" \
    --wall-seconds "$wall" || return $?

  assert_no_training_or_other_readout || return $?
  if ! run_tools "$SCRIPT" --config "$CONFIG" score-one \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      >"$job_rel/scoring.stdout.log" 2>&1
  then
    record_external_failure "$building_id" "$arm" "$run" "scoring" \
      "scoring or panel publication failed; see $job_rel/scoring.stdout.log"
    return 1
  fi
  return 0
}

run_extract_infra_retry() {
  local building_id="$1"
  local arm="$2"
  local run="$3"
  local gpu="$4"
  local job_rel="$READOUT_REL/by_building/$building_id/arm_$arm/$run"
  local attempt_rel="$job_rel/infra_retry_01"
  local started ended wall argv_text environment_text value
  local -a argv
  local -a environment_args

  assert_no_training_or_other_readout || return $?
  run_tools "$SCRIPT" --config "$CONFIG" --retry-policy "$RETRY_POLICY" \
    prepare-extract-infra-retry \
    --building-id "$building_id" --arm "$arm" --run "$run" || return $?
  if ! argv_text="$(
      run_tools "$SCRIPT" --config "$CONFIG" --retry-policy "$RETRY_POLICY" \
        retry-extract-argv \
        --building-id "$building_id" --arm "$arm" --run "$run"
    )"
  then
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-retry-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "failed to resolve immutable retry argv" || true
    return 1
  fi
  mapfile -t argv < <(printf '%s\n' "$argv_text")
  [[ "${#argv[@]}" -gt 1 ]] || {
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-retry-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "readout retry argv is empty" || true
    return 1
  }
  if ! environment_text="$(
      run_tools "$SCRIPT" --config "$CONFIG" --retry-policy "$RETRY_POLICY" \
        retry-extract-environment \
        --building-id "$building_id" --arm "$arm" --run "$run"
    )"
  then
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-retry-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "failed to resolve immutable retry environment" || true
    return 1
  fi
  environment_args=()
  while IFS= read -r value; do
    [[ -n "$value" ]] && environment_args+=(--env "$value")
  done < <(printf '%s\n' "$environment_text")
  [[ "${#environment_args[@]}" -eq 6 ]] || {
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-retry-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "retry environment does not contain exactly three variables" || true
    return 1
  }

  started="$(date +%s)"
  if ! docker run --rm \
      --pull=never \
      --network=none \
      --memory="$MEMORY_LIMIT" \
      --memory-swap="$MEMORY_LIMIT" \
      --shm-size=4g \
      --gpus "device=$gpu" \
      --user "$(id -u):$(id -g)" \
      --env CUDA_VISIBLE_DEVICES=0 \
      --env PYTHONDONTWRITEBYTECODE=1 \
      "${environment_args[@]}" \
      --volume "$ROOT:/workspace/JointBuildGS" \
      --workdir /workspace/JointBuildGS \
      --entrypoint python3 \
      "$READOUT_IMAGE" "${argv[@]}" \
      >"$attempt_rel/extract.stdout.log" 2>&1
  then
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-retry-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "point-cloud infrastructure retry failed; see $attempt_rel/extract.stdout.log" || true
    return 1
  fi
  ended="$(date +%s)"
  wall="$((ended - started))"
  if ! run_tools "$SCRIPT" --config "$CONFIG" accept-extract-infra-retry \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --wall-seconds "$wall"
  then
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-retry-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "readout retry output validation or adoption failed" || true
    return 1
  fi
  run_one "$building_id" "$arm" "$run" "$gpu" post-extract
}

run_extract_infra_recovery2() {
  local building_id="$1"
  local arm="$2"
  local run="$3"
  local gpu="$4"
  local job_rel="$READOUT_REL/by_building/$building_id/arm_$arm/$run"
  local attempt_rel="$job_rel/infra_retry_02"
  local started ended wall argv_text environment_text value
  local -a argv
  local -a environment_args

  assert_no_training_or_other_readout || return $?
  if ! run_tools "$SCRIPT" --config "$CONFIG" \
      --recovery2-policy "$RECOVERY2_POLICY" \
      prepare-extract-infra-recovery2 \
      --building-id "$building_id" --arm "$arm" --run "$run"
  then
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-recovery2-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "recovery2 preflight, cache seed, or authorization failed" || true
    return 1
  fi
  if ! argv_text="$(
      run_tools "$SCRIPT" --config "$CONFIG" \
        --recovery2-policy "$RECOVERY2_POLICY" \
        recovery2-extract-argv \
        --building-id "$building_id" --arm "$arm" --run "$run"
    )"
  then
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-recovery2-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "failed to resolve immutable recovery2 argv" || true
    return 1
  fi
  mapfile -t argv < <(printf '%s\n' "$argv_text")
  [[ "${#argv[@]}" -gt 1 ]] || {
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-recovery2-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "recovery2 argv is empty" || true
    return 1
  }
  if ! environment_text="$(
      run_tools "$SCRIPT" --config "$CONFIG" \
        --recovery2-policy "$RECOVERY2_POLICY" \
        recovery2-extract-environment \
        --building-id "$building_id" --arm "$arm" --run "$run"
    )"
  then
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-recovery2-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "failed to resolve immutable recovery2 environment" || true
    return 1
  fi
  environment_args=()
  while IFS= read -r value; do
    [[ -n "$value" ]] && environment_args+=(--env "$value")
  done < <(printf '%s\n' "$environment_text")
  [[ "${#environment_args[@]}" -eq 8 ]] || {
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-recovery2-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "recovery2 environment lacks the three cache variables plus MAX_JOBS=1" || true
    return 1
  }

  started="$(date +%s)"
  if ! docker run --rm \
      --pull=never \
      --network=none \
      --memory="$MEMORY_LIMIT" \
      --memory-swap="$MEMORY_LIMIT" \
      --shm-size=4g \
      --gpus "device=$gpu" \
      --user "$(id -u):$(id -g)" \
      --env CUDA_VISIBLE_DEVICES=0 \
      --env PYTHONDONTWRITEBYTECODE=1 \
      "${environment_args[@]}" \
      --volume "$ROOT:/workspace/JointBuildGS" \
      --workdir /workspace/JointBuildGS \
      --entrypoint python3 \
      "$READOUT_IMAGE" "${argv[@]}" \
      >"$attempt_rel/extract.stdout.log" 2>&1
  then
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-recovery2-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "point-cloud recovery2 failed; see $attempt_rel/extract.stdout.log" || true
    return 1
  fi
  ended="$(date +%s)"
  wall="$((ended - started))"
  if ! run_tools "$SCRIPT" --config "$CONFIG" \
      accept-extract-infra-recovery2 \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --wall-seconds "$wall"
  then
    run_tools "$SCRIPT" --config "$CONFIG" \
      record-extract-infra-recovery2-failure \
      --building-id "$building_id" --arm "$arm" --run "$run" \
      --message "recovery2 output validation or adoption failed" || true
    return 1
  fi
  run_one "$building_id" "$arm" "$run" "$gpu" post-extract
}

case "${1:-}" in
  test)
    verify_images
    run_tools -m unittest -v "$TEST"
    ;;
  check)
    verify_images
    if [[ -n "${2:-}" ]]; then
      [[ -n "${3:-}" && -n "${4:-}" ]] || {
        echo "usage: $0 check BUILDING_ID ARM RUN" >&2
        exit 2
      }
      run_tools "$SCRIPT" --config "$CONFIG" check \
        --building-id "$2" --arm "$3" --run "$4"
    else
      run_tools "$SCRIPT" --config "$CONFIG" check
    fi
    ;;
  one)
    [[ -n "${2:-}" && -n "${3:-}" && -n "${4:-}" && -n "${5:-}" ]] || {
      echo "usage: $0 one BUILDING_ID ARM RUN GPU" >&2
      exit 2
    }
    validate_gpu "$5"
    verify_images
    acquire_serial_lock
    run_one "$2" "$3" "$4" "$5"
    ;;
  retry-extract-infra)
    [[ -n "${2:-}" && -n "${3:-}" && -n "${4:-}" && -n "${5:-}" ]] || {
      echo "usage: $0 retry-extract-infra BUILDING_ID ARM RUN GPU" >&2
      exit 2
    }
    validate_gpu "$5"
    verify_images
    acquire_serial_lock
    run_extract_infra_retry "$2" "$3" "$4" "$5"
    ;;
  recover-extract-infra2)
    [[ -n "${2:-}" && -n "${3:-}" && -n "${4:-}" && -n "${5:-}" ]] || {
      echo "usage: $0 recover-extract-infra2 BUILDING_ID ARM RUN GPU" >&2
      exit 2
    }
    validate_gpu "$5"
    verify_images
    acquire_serial_lock
    run_extract_infra_recovery2 "$2" "$3" "$4" "$5"
    ;;
  all-ready)
    [[ -n "${2:-}" ]] || {
      echo "usage: $0 all-ready GPU" >&2
      exit 2
    }
    validate_gpu "$2"
    verify_images
    acquire_serial_lock
    run_tools "$SCRIPT" --config "$CONFIG" reconcile-counters >/dev/null
    if ! pending_text="$(
        run_tools "$SCRIPT" --config "$CONFIG" list-pending
      )"
    then
      echo "failed to resolve the fail-closed pending queue" >&2
      exit 1
    fi
    pending=()
    if [[ -n "$pending_text" ]]; then
      mapfile -t pending < <(printf '%s\n' "$pending_text")
    fi
    last_failure_stage=""
    last_failure_building=""
    failure_building_streak=0
    for key in "${pending[@]}"; do
      IFS=/ read -r building_id arm_part run <<<"$key"
      if run_one "$building_id" "${arm_part#arm_}" "$run" "$2"; then
        last_failure_stage=""
        last_failure_building=""
        failure_building_streak=0
        continue
      else
        run_status=$?
      fi
      if [[ "$run_status" -eq 75 ]]; then
        echo "readout queue paused by the serial/training process guard" >&2
        exit 75
      fi
      if [[ "$key" == "DEBY_LOD2_42364609/arm_A/r1" ]]; then
        echo "smoke readout failed; queue remains fail-closed" >&2
        exit 1
      fi
      if ! failure_stage="$(
          run_tools "$SCRIPT" --config "$CONFIG" failure-stage \
            --building-id "$building_id" \
            --arm "${arm_part#arm_}" \
            --run "$run"
        )"
      then
        echo "job failed without a readable immutable failure receipt: $key" >&2
        exit 1
      fi
      echo "recorded and skipped failed job without retry: $key stage=$failure_stage" >&2
      if [[ "$failure_stage" == "$last_failure_stage" \
          && "$building_id" != "$last_failure_building" ]]; then
        failure_building_streak=$((failure_building_streak + 1))
      else
        failure_building_streak=1
      fi
      last_failure_stage="$failure_stage"
      last_failure_building="$building_id"
      if [[ "$failure_building_streak" -ge "$CATASTROPHE_STOP_N" ]]; then
        echo "catastrophe stop: error stage $failure_stage repeated across $failure_building_streak consecutive buildings" >&2
        exit 1
      fi
    done
    ;;
  finalize-partial)
    verify_tools_image
    acquire_serial_lock
    run_tools "$SCRIPT" --config "$CONFIG" finalize-partial
    ;;
  *)
    echo "usage: $0 {test|check [BUILDING_ID ARM RUN]|one BUILDING_ID ARM RUN GPU|retry-extract-infra BUILDING_ID ARM RUN GPU|recover-extract-infra2 BUILDING_ID ARM RUN GPU|all-ready GPU|finalize-partial}" >&2
    exit 2
    ;;
esac
