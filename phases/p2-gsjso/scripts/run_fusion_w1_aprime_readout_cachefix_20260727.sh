#!/usr/bin/env bash
# Docker-only generic cache-fixed wrapper for the locked A-prime readout.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

CONFIG="phases/p2-gsjso/configs/fusion_w1_aprime_readout_cachefix_20260727.json"
ADAPTER="phases/p2-gsjso/scripts/fusion_w1_aprime_readout_cachefix_20260727.py"
BASE_DRIVER="phases/p2-gsjso/scripts/fusion_w1_aprime_readout_20260726.py"
TEST="phases/p2-gsjso/scripts/test_fusion_w1_aprime_readout_cachefix_20260727.py"
READOUT_ROOT="phases/p2-gsjso/runs/20260726_fusion_w1_aprime/readout"
RUNTIME_REL="phases/p2-gsjso/runs/20260726_fusion_w1_aprime/runtime_env"

DEV_IMAGE="jointbuildgs:dev"
DEV_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
TOOLS_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
MEMORY_LIMIT="24g"
CPU_LIMIT="12"
GPU_INDEX="${APRIME_READOUT_CACHEFIX_GPU_INDEX:-1}"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
[[ "$GPU_INDEX" == "1" ]] || {
  echo "A-prime cache-fixed readout is locked to physical GPU 1; observed APRIME_READOUT_CACHEFIX_GPU_INDEX=$GPU_INDEX" >&2
  exit 64
}
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
    --env "HOME=/workspace/JointBuildGS/$RUNTIME_REL/home" \
    --env "XDG_CACHE_HOME=/workspace/JointBuildGS/$RUNTIME_REL/xdg_cache" \
    --env "TORCH_EXTENSIONS_DIR=/workspace/JointBuildGS/$RUNTIME_REL/torch_extensions" \
    --env MAX_JOBS=2 \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --volume "$REPO_ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$DEV_IMAGE" "$@"
}

prepare_cache_paths() {
  local path
  for path in "$RUNTIME_REL/home" "$RUNTIME_REL/xdg_cache" "$RUNTIME_REL/torch_extensions"; do
    mkdir -p "$path"
    [[ -d "$path" && ! -L "$path" && -w "$path" ]] || {
      echo "shared T2 cache path is not a writable real directory: $path" >&2
      return 73
    }
  done
}

assert_no_training() {
  local pattern
  pattern='src/stage2/train.py|fusion_w1_aprime_training_20260726.py launch'
  if pgrep -af "$pattern" >/dev/null; then
    echo "training process guard matched; cache-fixed readout will not start" >&2
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

record_active_attempt_failure() {
  local error_type="$1"
  local message="$2"
  local attempt_rel=""
  local failure_rel=""
  local complete_rel=""
  local status=0

  [[ -n "${ACTIVE_ATTEMPT:-}" ]] || return 0
  [[ "${ACTIVE_FAILURE_CLOSED:-false}" != "true" ]] || return 0
  [[ "$ACTIVE_ATTEMPT" =~ ^[1-9][0-9]{0,2}$ ]] || {
    echo "cannot close invalid active readout attempt: $ACTIVE_ATTEMPT" >&2
    return 2
  }

  # Set the re-entry guard before invoking Docker-backed receipt publication.
  # The base producer is also idempotent when failure.json already exists, but
  # this guard prevents ERR and signal handlers from both invoking it.
  ACTIVE_FAILURE_CLOSED="true"
  attempt_rel="$READOUT_ROOT/by_building/$BUILDING_ID/arm_$ARM/$REPLICATE/attempts/attempt_$(printf '%03d' "$ACTIVE_ATTEMPT")"
  failure_rel="$attempt_rel/failure.json"
  complete_rel="$READOUT_ROOT/by_building/$BUILDING_ID/arm_$ARM/$REPLICATE/complete.json"

  if [[ -f "$complete_rel" && ! -L "$complete_rel" && -s "$complete_rel" ]]; then
    echo "authoritative readout complete already exists; suppressing late failure receipt: $complete_rel" >&2
    ACTIVE_ATTEMPT=""
    return 0
  fi
  if [[ -f "$failure_rel" && ! -L "$failure_rel" && -s "$failure_rel" ]]; then
    echo "active readout attempt already has a failure receipt: $failure_rel" >&2
    ACTIVE_ATTEMPT=""
    return 0
  fi

  base_tools record-failure \
    --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
    --attempt "$ACTIVE_ATTEMPT" --stage "$CURRENT_STAGE" \
    --message "$message" --error-type "$error_type" || status=$?
  if [[ "$status" -ne 0 ]]; then
    echo "failed to publish active readout failure receipt: status=$status" >&2
    return "$status"
  fi
  ACTIVE_ATTEMPT=""
  return 0
}

handle_wrapper_error() {
  local status="$1"
  local receipt_status=0
  trap - ERR
  trap '' TERM INT
  set +e
  record_active_attempt_failure \
    ExternalStageError \
    "cache-fixed wrapper stage exited nonzero: status=$status" || receipt_status=$?
  if [[ "$receipt_status" -ne 0 ]]; then
    echo "readout failure receipt publication also failed: status=$receipt_status" >&2
  fi
  exit "$status"
}

handle_wrapper_signal() {
  local signal_name="$1"
  local status="$2"
  local receipt_status=0
  trap - ERR
  trap '' TERM INT
  set +e
  record_active_attempt_failure \
    ExternalSignal \
    "cache-fixed wrapper interrupted by $signal_name" || receipt_status=$?
  if [[ "$receipt_status" -ne 0 ]]; then
    echo "readout signal failure receipt publication failed: status=$receipt_status" >&2
  fi
  exit "$status"
}

base_tools() {
  run_tools "$BASE_DRIVER" --config "$CONFIG" "$@"
}

base_control() {
  run_control "$BASE_DRIVER" --config "$CONFIG" "$@"
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
  base_tools authorize-roofer \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt" --mode "$mode"
  mapfile -t paths < <(
    base_tools roofer-paths \
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
  base_tools accept-roofer \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt" --mode "$mode" --wall-seconds "$wall_seconds"
  CURRENT_STAGE="${mode}_score"
  base_tools score \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt" --mode "$mode"
}

run_one() {
  local building_id="$1"
  local arm="$2"
  local replicate="$3"
  local attempt=""
  local attempt_rel=""
  local started ended wall_seconds alpha_disposition value
  local -a argv environment env_args=()

  CURRENT_STAGE="preflight"
  assert_no_training
  prepare_cache_paths
  run_control "$ADAPTER" --config "$CONFIG" validate-config
  CURRENT_STAGE="cache_probe"
  run_dev "$ADAPTER" --config "$CONFIG" cache-probe
  CURRENT_STAGE="base_check"
  base_control check \
    --building-id "$building_id" --arm "$arm" --run "$replicate"

  CURRENT_STAGE="begin_attempt"
  attempt="$(base_control begin \
    --building-id "$building_id" --arm "$arm" --run "$replicate")"
  [[ "$attempt" =~ ^[1-9][0-9]{0,2}$ ]] || {
    echo "invalid attempt number from base driver: $attempt" >&2
    return 1
  }
  ACTIVE_ATTEMPT="$attempt"
  attempt_rel="$READOUT_ROOT/by_building/$building_id/arm_$arm/$replicate/attempts/attempt_$(printf '%03d' "$attempt")"

  CURRENT_STAGE="primary_tsdf"
  mapfile -t argv < <(
    base_tools tsdf-argv \
      --building-id "$building_id" --arm "$arm" --run "$replicate" \
      --attempt "$attempt"
  )
  mkdir -p "$attempt_rel/tsdf"
  started="$(date +%s)"
  run_dev "${argv[@]}" 2>&1 | tee "$attempt_rel/tsdf/tsdf.stdout.log"
  ended="$(date +%s)"
  printf '%s\n' "$((ended - started))" >"$attempt_rel/tsdf/wall_seconds.txt"

  CURRENT_STAGE="primary_prepare"
  base_tools prepare-primary \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt"
  run_roofer_and_score "$building_id" "$arm" "$replicate" "$attempt" primary

  CURRENT_STAGE="legacy_alpha_authorize"
  base_tools authorize-alpha-extract \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt"
  mapfile -t argv < <(
    base_tools alpha-extract-argv \
      --building-id "$building_id" --arm "$arm" --run "$replicate" \
      --attempt "$attempt"
  )
  mapfile -t environment < <(
    base_tools alpha-extract-environment \
      --building-id "$building_id" --arm "$arm" --run "$replicate" \
      --attempt "$attempt"
  )
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
    --env PYTHONDONTWRITEBYTECODE=1 \
    --volume "$REPO_ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$DEV_IMAGE" "${argv[@]}" \
    >"$attempt_rel/legacy_alpha/extract.stdout.log" 2>&1
  ended="$(date +%s)"
  wall_seconds="$((ended - started))"
  CURRENT_STAGE="legacy_alpha_extract_accept"
  base_tools accept-alpha-extract \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt" --wall-seconds "$wall_seconds"

  CURRENT_STAGE="legacy_alpha_classification_authorize"
  base_tools authorize-alpha-classification \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt"
  mapfile -t argv < <(
    base_tools alpha-classification-argv \
      --building-id "$building_id" --arm "$arm" --run "$replicate" \
      --attempt "$attempt"
  )
  CURRENT_STAGE="legacy_alpha_classification"
  started="$(date +%s)"
  run_tools "${argv[@]}" >"$attempt_rel/legacy_alpha/classification.stdout.log" 2>&1
  ended="$(date +%s)"
  wall_seconds="$((ended - started))"
  CURRENT_STAGE="legacy_alpha_classification_accept"
  base_tools accept-alpha-classification \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt" --wall-seconds "$wall_seconds"
  alpha_disposition="$(base_tools alpha-disposition \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt")"
  if [[ "$alpha_disposition" == "ASSEMBLE" ]]; then
    run_roofer_and_score "$building_id" "$arm" "$replicate" "$attempt" legacy_alpha
  elif [[ "$alpha_disposition" == "NOT_ASSEMBLED" ]]; then
    CURRENT_STAGE="legacy_alpha_not_assembled_observation"
  else
    echo "unknown legacy alpha disposition: $alpha_disposition" >&2
    return 1
  fi

  CURRENT_STAGE="finalize_hygiene"
  run_control "$ADAPTER" --config "$CONFIG" quarantine-locks \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt"
  run_control "$ADAPTER" --config "$CONFIG" verify-hygiene \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt"
  CURRENT_STAGE="finalize"
  base_tools finalize \
    --building-id "$building_id" --arm "$arm" --run "$replicate" \
    --attempt "$attempt"
  ACTIVE_ATTEMPT=""
}

verify_images

case "${1:-}" in
  test)
    run_tools -m unittest -v "$TEST"
    ;;
  cache-check)
    assert_no_training
    prepare_cache_paths
    run_control "$ADAPTER" --config "$CONFIG" validate-config
    run_dev "$ADAPTER" --config "$CONFIG" cache-probe
    ;;
  check)
    [[ -n "${2:-}" && -n "${3:-}" && -n "${4:-}" ]] || {
      echo "usage: $0 check DEBY_LOD2_<id> {Aprime|B} {r1|r2}" >&2
      exit 2
    }
    run_control "$ADAPTER" --config "$CONFIG" validate-config
    base_control check --building-id "$2" --arm "$3" --run "$4"
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
    ACTIVE_FAILURE_CLOSED="false"
    CURRENT_STAGE="startup"
    trap 'handle_wrapper_error "$?"' ERR
    trap 'handle_wrapper_signal TERM 143' TERM
    trap 'handle_wrapper_signal INT 130' INT
    run_one "$BUILDING_ID" "$ARM" "$REPLICATE"
    trap - ERR TERM INT
    ;;
  *)
    echo "usage: $0 {test|cache-check|check BUILDING ARM RUN|one BUILDING ARM RUN}" >&2
    exit 2
    ;;
esac
