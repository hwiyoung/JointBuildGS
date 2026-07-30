#!/usr/bin/env bash
# Docker-only, serial production readout for Fusion-W1 A-prime.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

CONFIG="phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_readout_20260726.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_readout_20260726.py"
TEST="tests/fusion_w1/test_fusion_w1_aprime_readout_20260726.py"
READOUT_ROOT="phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/readout"
DEV_IMAGE="jointbuildgs:dev"
DEV_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
TOOLS_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
MEMORY_LIMIT="24g"
CPU_LIMIT="12"
GPU_INDEX="${APRIME_READOUT_GPU_INDEX:-0}"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
ROOFER_PARAMETERS=(
  --id-attribute building_id
  --jobs 3
  --srs EPSG:25832
  --bld-class 6
  --grnd-class 2
  --lod22
)

container_path() {
  printf '/workspace/JointBuildGS/%s' "$1"
}

verify_images() {
  local observed
  observed="$(docker image inspect "$DEV_IMAGE" --format '{{.Id}}')"
  [[ "$observed" == "$DEV_IMAGE_ID" ]] || {
    echo "dev image ID mismatch: $observed" >&2
    return 2
  }
  observed="$(docker image inspect "$TOOLS_IMAGE" --format '{{.Id}}')"
  [[ "$observed" == "$TOOLS_IMAGE_ID" ]] || {
    echo "tools image ID mismatch: $observed" >&2
    return 2
  }
  docker image inspect "$ROOFER_IMAGE" >/dev/null
}

run_tools() {
  docker run --rm \
    --pull=never \
    --network=none \
    --memory="$MEMORY_LIMIT" \
    --memory-swap="$MEMORY_LIMIT" \
    --cpus="$CPU_LIMIT" \
    --shm-size=4g \
    --user "$HOST_UID:$HOST_GID" \
    --env MPLCONFIGDIR=/tmp/matplotlib \
    --env XDG_CACHE_HOME=/tmp/cache \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --volume "$REPO_ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$TOOLS_IMAGE" "$@"
}

# The strict training-binding check imports the locked training driver, whose
# config parser requires PyYAML.  Keep that control-only step in the pinned dev
# image; geometry, LAS, scoring, and report commands remain in the tools image.
run_control() {
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
    "$DEV_IMAGE" "$@"
}

run_dev() {
  docker run --rm \
    --pull=never \
    --network=none \
    --gpus all \
    --memory="$MEMORY_LIMIT" \
    --memory-swap="$MEMORY_LIMIT" \
    --cpus="$CPU_LIMIT" \
    --shm-size=4g \
    --user "$HOST_UID:$HOST_GID" \
    --env "CUDA_VISIBLE_DEVICES=$GPU_INDEX" \
    --env "APRIME_CONTAINER_IMAGE=$DEV_IMAGE" \
    --env "APRIME_CONTAINER_IMAGE_ID=$DEV_IMAGE_ID" \
    --volume "$REPO_ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$DEV_IMAGE" "$@"
}

assert_no_training() {
  local pattern
  pattern='src/stage2/train.py|fusion_w1_aprime_training_20260726.py launch'
  if pgrep -af "$pattern" >/dev/null; then
    echo "training process guard matched; readout will not start" >&2
    pgrep -af "$pattern" >&2 || true
    return 75
  fi
}

acquire_driver_lock() {
  mkdir -p "$READOUT_ROOT"
  exec 9>"$READOUT_ROOT/driver.lock"
  if ! flock -n 9; then
    echo "A-prime readout driver lock is already held" >&2
    exit 75
  fi
}

run_roofer_and_score() {
  local building_id="$1"
  local arm="$2"
  local replicate="$3"
  local attempt="$4"
  local mode="$5"
  local attempt_rel="$READOUT_ROOT/by_building/$building_id/arm_$arm/$replicate/attempts/attempt_$(printf '%03d' "$attempt")"
  local log_rel="$attempt_rel/$mode/roofer.stdout.log"
  local started ended wall_seconds
  local -a paths

  CURRENT_STAGE="${mode}_roofer_authorize"
  run_tools "$SCRIPT" --config "$CONFIG" authorize-roofer \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt" --mode "$mode"
  mapfile -t paths < <(
    run_tools "$SCRIPT" --config "$CONFIG" roofer-paths \
      --building-id "$building_id" --arm "$arm" --run "$replicate" \
      --attempt "$attempt" --mode "$mode"
  )
  [[ "${#paths[@]}" -eq 3 ]] || {
    echo "expected three Roofer paths, observed ${#paths[@]}" >&2
    return 1
  }
  mkdir -p "$(dirname "$log_rel")"
  CURRENT_STAGE="${mode}_roofer"
  started="$(date +%s)"
  docker run --rm \
    --pull=never \
    --network=none \
    --memory="$MEMORY_LIMIT" \
    --memory-swap="$MEMORY_LIMIT" \
    --cpus="$CPU_LIMIT" \
    --user "$HOST_UID:$HOST_GID" \
    --volume "$REPO_ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    "$ROOFER_IMAGE" \
    "${ROOFER_PARAMETERS[@]}" \
    "$(container_path "${paths[0]}")" \
    "$(container_path "${paths[1]}")" \
    "$(container_path "${paths[2]}")" \
    >"$log_rel" 2>&1
  ended="$(date +%s)"
  wall_seconds="$((ended - started))"
  CURRENT_STAGE="${mode}_roofer_accept"
  run_tools "$SCRIPT" --config "$CONFIG" accept-roofer \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt" --mode "$mode" --wall-seconds "$wall_seconds"
  CURRENT_STAGE="${mode}_score"
  run_tools "$SCRIPT" --config "$CONFIG" score \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt" --mode "$mode"
}

run_one() {
  local building_id="$1"
  local arm="$2"
  local replicate="$3"
  local attempt=""
  local attempt_rel=""
  local started ended wall_seconds
  local -a argv environment

  CURRENT_STAGE="preflight"
  assert_no_training
  run_control "$SCRIPT" --config "$CONFIG" check \
    --building-id "$building_id" --arm "$arm" --run "$replicate"
  CURRENT_STAGE="begin_attempt"
  attempt="$(run_control "$SCRIPT" --config "$CONFIG" begin \
    --building-id "$building_id" --arm "$arm" --run "$replicate")"
  [[ "$attempt" =~ ^[1-9][0-9]{0,2}$ ]] || {
    echo "invalid attempt number from driver: $attempt" >&2
    return 1
  }
  ACTIVE_ATTEMPT="$attempt"
  attempt_rel="$READOUT_ROOT/by_building/$building_id/arm_$arm/$replicate/attempts/attempt_$(printf '%03d' "$attempt")"

  CURRENT_STAGE="primary_tsdf"
  mapfile -t argv < <(
    run_tools "$SCRIPT" --config "$CONFIG" tsdf-argv \
      --building-id "$building_id" --arm "$arm" --run "$replicate" --attempt "$attempt"
  )
  mkdir -p "$attempt_rel/tsdf"
  started="$(date +%s)"
  run_dev "${argv[@]}" 2>&1 | tee "$attempt_rel/tsdf/tsdf.stdout.log"
  ended="$(date +%s)"
  printf '%s\n' "$((ended - started))" >"$attempt_rel/tsdf/wall_seconds.txt"

  CURRENT_STAGE="primary_prepare"
  run_tools "$SCRIPT" --config "$CONFIG" prepare-primary \
    --building-id "$building_id" --arm "$arm" --run "$replicate" --attempt "$attempt"
  run_roofer_and_score "$building_id" "$arm" "$replicate" "$attempt" primary

  CURRENT_STAGE="legacy_alpha_authorize"
  run_tools "$SCRIPT" --config "$CONFIG" authorize-alpha-extract \
    --building-id "$building_id" --arm "$arm" --run "$replicate" --attempt "$attempt"
  mapfile -t argv < <(
    run_tools "$SCRIPT" --config "$CONFIG" alpha-extract-argv \
      --building-id "$building_id" --arm "$arm" --run "$replicate" --attempt "$attempt"
  )
  mapfile -t environment < <(
    run_tools "$SCRIPT" --config "$CONFIG" alpha-extract-environment \
      --building-id "$building_id" --arm "$arm" --run "$replicate" --attempt "$attempt"
  )
  local -a env_args=()
  local value
  for value in "${environment[@]}"; do
    env_args+=(--env "$value")
  done
  CURRENT_STAGE="legacy_alpha_extract"
  started="$(date +%s)"
  docker run --rm \
    --pull=never \
    --network=none \
    --gpus all \
    --memory="$MEMORY_LIMIT" \
    --memory-swap="$MEMORY_LIMIT" \
    --cpus="$CPU_LIMIT" \
    --shm-size=4g \
    --user "$HOST_UID:$HOST_GID" \
    --env "CUDA_VISIBLE_DEVICES=$GPU_INDEX" \
    "${env_args[@]}" \
    --volume "$REPO_ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$DEV_IMAGE" "${argv[@]}" \
    >"$attempt_rel/legacy_alpha/extract.stdout.log" 2>&1
  ended="$(date +%s)"
  wall_seconds="$((ended - started))"
  CURRENT_STAGE="legacy_alpha_extract_accept"
  run_tools "$SCRIPT" --config "$CONFIG" accept-alpha-extract \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt" --wall-seconds "$wall_seconds"

  CURRENT_STAGE="legacy_alpha_classification_authorize"
  run_tools "$SCRIPT" --config "$CONFIG" authorize-alpha-classification \
    --building-id "$building_id" --arm "$arm" --run "$replicate" --attempt "$attempt"
  mapfile -t argv < <(
    run_tools "$SCRIPT" --config "$CONFIG" alpha-classification-argv \
      --building-id "$building_id" --arm "$arm" --run "$replicate" --attempt "$attempt"
  )
  CURRENT_STAGE="legacy_alpha_classification"
  started="$(date +%s)"
  run_tools "${argv[@]}" >"$attempt_rel/legacy_alpha/classification.stdout.log" 2>&1
  ended="$(date +%s)"
  wall_seconds="$((ended - started))"
  CURRENT_STAGE="legacy_alpha_classification_accept"
  run_tools "$SCRIPT" --config "$CONFIG" accept-alpha-classification \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt" --wall-seconds "$wall_seconds"
  local alpha_disposition
  alpha_disposition="$(run_tools "$SCRIPT" --config "$CONFIG" alpha-disposition \
    --building-id "$building_id" --arm "$arm" --run "$replicate" --attempt "$attempt")"
  if [[ "$alpha_disposition" == "ASSEMBLE" ]]; then
    run_roofer_and_score "$building_id" "$arm" "$replicate" "$attempt" legacy_alpha
  elif [[ "$alpha_disposition" == "NOT_ASSEMBLED" ]]; then
    CURRENT_STAGE="legacy_alpha_not_assembled_observation"
  else
    echo "unknown legacy alpha disposition: $alpha_disposition" >&2
    return 1
  fi

  CURRENT_STAGE="finalize"
  run_tools "$SCRIPT" --config "$CONFIG" finalize \
    --building-id "$building_id" --arm "$arm" --run "$replicate" --attempt "$attempt"
  ACTIVE_ATTEMPT=""
}

verify_images

case "${1:-}" in
  test)
    run_tools -m unittest -v "$TEST"
    ;;
  check)
    [[ -n "${2:-}" && -n "${3:-}" && -n "${4:-}" ]] || {
      echo "usage: $0 check DEBY_LOD2_<id> {Aprime|B} {r1|r2}" >&2
      exit 2
    }
    run_control "$SCRIPT" --config "$CONFIG" check \
      --building-id "$2" --arm "$3" --run "$4"
    ;;
  one)
    [[ -n "${2:-}" && -n "${3:-}" && -n "${4:-}" ]] || {
      echo "usage: $0 one DEBY_LOD2_<id> {Aprime|B} {r1|r2}" >&2
      exit 2
    }
    acquire_driver_lock
    BUILDING_ID="$2"
    ARM="$3"
    REPLICATE="$4"
    ACTIVE_ATTEMPT=""
    CURRENT_STAGE="startup"
    trap 'status=$?; trap - ERR; if [[ -n "$ACTIVE_ATTEMPT" ]]; then run_tools "$SCRIPT" --config "$CONFIG" record-failure --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" --attempt "$ACTIVE_ATTEMPT" --stage "$CURRENT_STAGE" --message "wrapper stage exited nonzero: status=$status" --error-type ExternalStageError || true; fi; exit "$status"' ERR
    run_one "$BUILDING_ID" "$ARM" "$REPLICATE"
    trap - ERR
    ;;
  *)
    echo "usage: $0 {test|check BUILDING ARM RUN|one BUILDING ARM RUN}" >&2
    exit 2
    ;;
esac
