#!/usr/bin/env bash
# Docker-only, serial T3 P0-prime A-prime driver. Learning and inference: zero.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

CONFIG="phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_p0prime_20260726.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_p0prime_20260726.py"
TEST="tests/fusion_w1/test_fusion_w1_aprime_p0prime_20260726.py"
T3_REL="phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/preflight/T3"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
TOOLS_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
MEMORY_LIMIT="24g"
ROOFER_PARAMETERS=(
  --id-attribute building_id
  --jobs 3
  --srs EPSG:25832
  --bld-class 6
  --grnd-class 2
  --lod22
)

observed_tools="$(docker image inspect "$TOOLS_IMAGE" --format '{{.Id}}')"
if [[ "$observed_tools" != "$TOOLS_IMAGE_ID" ]]; then
  echo "tools image ID mismatch: $observed_tools" >&2
  exit 2
fi
docker image inspect "$ROOFER_IMAGE" >/dev/null

run_tools() {
  docker run --rm \
    --pull=never \
    --network=none \
    --memory="$MEMORY_LIMIT" \
    --memory-swap="$MEMORY_LIMIT" \
    --shm-size=4g \
    --user "$(id -u):$(id -g)" \
    --env MPLCONFIGDIR=/tmp/matplotlib \
    --env XDG_CACHE_HOME=/tmp/cache \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --volume "$REPO_ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$TOOLS_IMAGE" "$@"
}

container_path() {
  printf "/workspace/JointBuildGS/%s" "$1"
}

assert_no_learning_or_other_readout() {
  local process_pattern
  process_pattern='src.stage2.train|/src/stage2/train.py|fusion_w1_training|fusion_w1_readout|pilot_1wave_postprocess_driver|run_primary4_assembly_validation|overnight_genclose.py'
  if pgrep -af "$process_pattern" >/dev/null; then
    echo "learning/readout process guard matched; T3 will not start" >&2
    pgrep -af "$process_pattern" >&2 || true
    return 75
  fi
}

acquire_driver_lock() {
  mkdir -p "$T3_REL"
  exec 9>"$T3_REL/driver.lock"
  if ! flock -n 9; then
    echo "T3 P0-prime driver lock is already held" >&2
    exit 75
  fi
}

record_external_failure() {
  local building_id="$1"
  local stage="$2"
  local message="$3"
  run_tools "$SCRIPT" --config "$CONFIG" record-failure \
    --building-id "$building_id" \
    --stage "$stage" \
    --message "$message" || true
}

run_one() {
  local building_id="$1"
  local job_rel="$T3_REL/by_building/$building_id"
  local roofer_log="$job_rel/roofer.stdout.log"
  local started ended wall_seconds
  local -a paths

  assert_no_learning_or_other_readout
  run_tools "$SCRIPT" --config "$CONFIG" prepare-one \
    --building-id "$building_id"
  run_tools "$SCRIPT" --config "$CONFIG" authorize-roofer \
    --building-id "$building_id"
  mapfile -t paths < <(
    run_tools "$SCRIPT" --config "$CONFIG" roofer-paths \
      --building-id "$building_id"
  )
  if [[ "${#paths[@]}" -ne 3 ]]; then
    record_external_failure "$building_id" "roofer_path_resolution" \
      "expected three Roofer paths, observed ${#paths[@]}"
    return 1
  fi

  started="$(date +%s)"
  if ! docker run --rm \
      --pull=never \
      --network=none \
      --memory="$MEMORY_LIMIT" \
      --memory-swap="$MEMORY_LIMIT" \
      --user "$(id -u):$(id -g)" \
      --volume "$REPO_ROOT:/workspace/JointBuildGS" \
      --workdir /workspace/JointBuildGS \
      "$ROOFER_IMAGE" \
      "${ROOFER_PARAMETERS[@]}" \
      "$(container_path "${paths[0]}")" \
      "$(container_path "${paths[1]}")" \
      "$(container_path "${paths[2]}")" \
      >"$roofer_log" 2>&1
  then
    record_external_failure "$building_id" "roofer" \
      "Roofer exited nonzero; see $roofer_log"
    return 1
  fi
  ended="$(date +%s)"
  wall_seconds="$((ended - started))"

  run_tools "$SCRIPT" --config "$CONFIG" accept-roofer \
    --building-id "$building_id" \
    --wall-seconds "$wall_seconds"
  run_tools "$SCRIPT" --config "$CONFIG" score-one \
    --building-id "$building_id"
}

case "${1:-}" in
  test)
    run_tools -m unittest -v "$TEST"
    ;;
  check)
    if [[ -n "${2:-}" ]]; then
      run_tools "$SCRIPT" --config "$CONFIG" check \
        --building-id "$2" --deep
    else
      run_tools "$SCRIPT" --config "$CONFIG" check
    fi
    ;;
  one)
    [[ -n "${2:-}" ]] || {
      echo "usage: $0 one DEBY_LOD2_<id>" >&2
      exit 2
    }
    acquire_driver_lock
    run_one "$2"
    ;;
  all-ready)
    acquire_driver_lock
    mapfile -t pending < <(
      run_tools "$SCRIPT" --config "$CONFIG" list-pending
    )
    for building_id in "${pending[@]}"; do
      if ! run_one "$building_id"; then
        record_external_failure "$building_id" "pipeline" \
          "T3 per-building pipeline did not complete; partial artifacts retained"
      fi
    done
    ;;
  finalize)
    acquire_driver_lock
    run_tools "$SCRIPT" --config "$CONFIG" finalize
    ;;
  finalize-all)
    acquire_driver_lock
    run_tools "$SCRIPT" --config "$CONFIG" finalize --require-all
    ;;
  *)
    echo "usage: $0 {test|check [BUILDING_ID]|one BUILDING_ID|all-ready|finalize|finalize-all}" >&2
    exit 2
    ;;
esac
