#!/usr/bin/env bash
# Docker-only continuation of one completed-training A-prime smoke job.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

CONFIG="phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_smoke_recovery_20260727.json"
ADAPTER="phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_smoke_recovery_20260727.py"
BASE_DRIVER="phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_readout_20260726.py"
TEST="tests/fusion_w1/test_fusion_w1_aprime_smoke_recovery_20260727.py"
RECOVERY_ROOT="phases/p2-gsjso/runs/fusion_w1/20260727_fusion_w1_aprime_smoke_recovery"
READOUT_ROOT="$RECOVERY_ROOT/readout"
DERIVED_CONFIG="$RECOVERY_ROOT/derived_readout_config_retry5.json"
RUNTIME_REL="phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/runtime_env"
BUILDING_ID="DEBY_LOD2_42364609"
ARM="Aprime"
REPLICATE="r1"
ATTEMPT="5"

DEV_IMAGE="jointbuildgs:dev"
DEV_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
TOOLS_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
MEMORY_LIMIT="24g"
CPU_LIMIT="12"
GPU_INDEX="${APRIME_SMOKE_RECOVERY_GPU_INDEX:-1}"
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
    echo "training process guard matched; smoke recovery will not start" >&2
    pgrep -af "$pattern" >&2 || true
    return 75
  fi
}

acquire_driver_lock() {
  mkdir -p "$READOUT_ROOT"
  exec 9>"$READOUT_ROOT/driver.lock"
  if ! flock -n 9; then
    echo "A-prime smoke recovery driver lock is already held" >&2
    exit 75
  fi
}

base() {
  run_tools "$BASE_DRIVER" --config "$DERIVED_CONFIG" "$@"
}

run_roofer_and_score() {
  local mode="$1"
  local attempt_rel="$READOUT_ROOT/by_building/$BUILDING_ID/arm_$ARM/$REPLICATE/attempts/attempt_$(printf '%03d' "$ATTEMPT")"
  local log_rel="$attempt_rel/$mode/roofer.stdout.log"
  local started ended wall_seconds
  local -a paths

  CURRENT_STAGE="${mode}_roofer_authorize"
  base authorize-roofer \
    --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
    --attempt "$ATTEMPT" --mode "$mode"
  mapfile -t paths < <(
    base roofer-paths \
      --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
      --attempt "$ATTEMPT" --mode "$mode"
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
  base accept-roofer \
    --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
    --attempt "$ATTEMPT" --mode "$mode" --wall-seconds "$wall_seconds"
  CURRENT_STAGE="${mode}_score"
  base score \
    --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
    --attempt "$ATTEMPT" --mode "$mode"
}

run_one() {
  local attempt_rel="$READOUT_ROOT/by_building/$BUILDING_ID/arm_$ARM/$REPLICATE/attempts/attempt_$(printf '%03d' "$ATTEMPT")"
  local started ended wall_seconds alpha_disposition value
  local -a argv environment env_args=()

  CURRENT_STAGE="preflight"
  assert_no_training
  prepare_cache_paths
  run_control "$ADAPTER" --config "$CONFIG" check
  run_control "$ADAPTER" --config "$CONFIG" prepare
  CURRENT_STAGE="cache_probe"
  run_dev "$ADAPTER" --config "$CONFIG" cache-probe

  CURRENT_STAGE="begin_attempt"
  run_control "$ADAPTER" --config "$CONFIG" begin
  ACTIVE_ATTEMPT="$ATTEMPT"

  CURRENT_STAGE="primary_tsdf"
  mapfile -t argv < <(
    base tsdf-argv \
      --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
      --attempt "$ATTEMPT"
  )
  mkdir -p "$attempt_rel/tsdf"
  started="$(date +%s)"
  run_dev "${argv[@]}" 2>&1 | tee "$attempt_rel/tsdf/tsdf.stdout.log"
  ended="$(date +%s)"
  printf '%s\n' "$((ended - started))" >"$attempt_rel/tsdf/wall_seconds.txt"

  CURRENT_STAGE="primary_prepare"
  base prepare-primary \
    --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
    --attempt "$ATTEMPT"
  run_roofer_and_score primary

  CURRENT_STAGE="legacy_alpha_authorize"
  base authorize-alpha-extract \
    --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
    --attempt "$ATTEMPT"
  mapfile -t argv < <(
    base alpha-extract-argv \
      --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
      --attempt "$ATTEMPT"
  )
  mapfile -t environment < <(
    base alpha-extract-environment \
      --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
      --attempt "$ATTEMPT"
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
    --volume "$REPO_ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$DEV_IMAGE" "${argv[@]}" \
    >"$attempt_rel/legacy_alpha/extract.stdout.log" 2>&1
  ended="$(date +%s)"
  wall_seconds="$((ended - started))"
  CURRENT_STAGE="legacy_alpha_extract_accept"
  base accept-alpha-extract \
    --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
    --attempt "$ATTEMPT" --wall-seconds "$wall_seconds"

  CURRENT_STAGE="legacy_alpha_classification_authorize"
  base authorize-alpha-classification \
    --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
    --attempt "$ATTEMPT"
  mapfile -t argv < <(
    base alpha-classification-argv \
      --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
      --attempt "$ATTEMPT"
  )
  CURRENT_STAGE="legacy_alpha_classification"
  started="$(date +%s)"
  run_tools "${argv[@]}" >"$attempt_rel/legacy_alpha/classification.stdout.log" 2>&1
  ended="$(date +%s)"
  wall_seconds="$((ended - started))"
  CURRENT_STAGE="legacy_alpha_classification_accept"
  base accept-alpha-classification \
    --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
    --attempt "$ATTEMPT" --wall-seconds "$wall_seconds"
  alpha_disposition="$(base alpha-disposition \
    --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
    --attempt "$ATTEMPT")"
  if [[ "$alpha_disposition" == "ASSEMBLE" ]]; then
    run_roofer_and_score legacy_alpha
  elif [[ "$alpha_disposition" == "NOT_ASSEMBLED" ]]; then
    CURRENT_STAGE="legacy_alpha_not_assembled_observation"
  else
    echo "unknown legacy alpha disposition: $alpha_disposition" >&2
    return 1
  fi

  CURRENT_STAGE="finalize_hygiene"
  run_control "$ADAPTER" --config "$CONFIG" quarantine-locks
  CURRENT_STAGE="finalize"
  base finalize \
    --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" \
    --attempt "$ATTEMPT"
  ACTIVE_ATTEMPT=""
  CURRENT_STAGE="publish"
  run_control "$ADAPTER" --config "$CONFIG" publish
  CURRENT_STAGE="verify"
  run_control "$ADAPTER" --config "$CONFIG" verify
}

verify_images

case "${1:-}" in
  test)
    run_tools -m unittest -v "$TEST"
    ;;
  check)
    run_control "$ADAPTER" --config "$CONFIG" check
    ;;
  cache-check)
    assert_no_training
    prepare_cache_paths
    run_control "$ADAPTER" --config "$CONFIG" prepare
    run_dev "$ADAPTER" --config "$CONFIG" cache-probe
    ;;
  one)
    [[ "$#" -eq 1 ]] || {
      echo "usage: $0 one" >&2
      exit 2
    }
    acquire_driver_lock
    ACTIVE_ATTEMPT=""
    CURRENT_STAGE="startup"
    trap 'status=$?; trap - ERR; if [[ -n "$ACTIVE_ATTEMPT" ]]; then base record-failure --building-id "$BUILDING_ID" --arm "$ARM" --run "$REPLICATE" --attempt "$ACTIVE_ATTEMPT" --stage "$CURRENT_STAGE" --message "wrapper stage exited nonzero: status=$status" --error-type ExternalStageError || true; fi; exit "$status"' ERR
    run_one
    trap - ERR
    ;;
  verify)
    run_control "$ADAPTER" --config "$CONFIG" verify
    ;;
  *)
    echo "usage: $0 {test|check|cache-check|one|verify}" >&2
    exit 2
    ;;
esac
