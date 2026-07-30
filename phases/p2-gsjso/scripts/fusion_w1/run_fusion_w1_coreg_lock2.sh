#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
CONFIG="phases/p2-gsjso/configs/fusion_w1/fusion_w1_coreg_lock1.json"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
DEV_IMAGE="jointbuildgs:dev"
TOOLS_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
DEV_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
MEMORY="24g"

require_image() {
  local image="$1"
  local expected="$2"
  local observed
  observed="$(docker image inspect "$image" --format '{{.Id}}')"
  if [[ "$observed" != "$expected" ]]; then
    echo "image ID mismatch for $image: $observed != $expected" >&2
    exit 2
  fi
}

require_image "$TOOLS_IMAGE" "$TOOLS_IMAGE_ID"
require_image "$DEV_IMAGE" "$DEV_IMAGE_ID"

run_tools() {
  docker run --rm \
    --memory="$MEMORY" --memory-swap="$MEMORY" \
    --user "$(id -u):$(id -g)" \
    -v "$ROOT:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    "$TOOLS_IMAGE" \
    python3 phases/p2-gsjso/scripts/fusion_w1/fusion_w1_coreg_lock1.py \
    --config "$CONFIG" --recovery-lock2 "$@"
}

run_dev() {
  docker run --rm \
    --memory="$MEMORY" --memory-swap="$MEMORY" \
    --shm-size=8g \
    --user "$(id -u):$(id -g)" \
    -v "$ROOT:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    "$DEV_IMAGE" \
    python3 phases/p2-gsjso/scripts/fusion_w1/fusion_w1_coreg_lock1.py \
    --config "$CONFIG" --recovery-lock2 "$@"
}

case "${1:-}" in
  prepare-als)
    run_tools prepare-als
    ;;
  prepare-controls)
    run_dev prepare-controls
    ;;
  measure)
    status=0
    run_dev verify || status=$?
    if [[ "$status" -eq 0 ]]; then run_tools prepare-als || status=$?; fi
    if [[ "$status" -eq 0 ]]; then run_dev fit || status=$?; fi
    if [[ "$status" -eq 0 ]]; then run_dev select || status=$?; fi
    if [[ "$status" -eq 0 ]]; then run_dev fit-blocks || status=$?; fi
    if [[ "$status" -eq 0 ]]; then run_dev select-blocks || status=$?; fi
    if [[ "$status" -eq 0 ]]; then run_dev check || status=$?; fi
    if [[ "$status" -eq 0 ]]; then run_dev publish-poses || status=$?; fi
    run_dev publish-small || true
    exit "$status"
    ;;
  verify)
    run_dev verify
    ;;
  test)
    docker run --rm \
      --memory="$MEMORY" --memory-swap="$MEMORY" \
      --shm-size=8g \
      --user "$(id -u):$(id -g)" \
      -v "$ROOT:/workspace/JointBuildGS:ro" \
      -w /workspace/JointBuildGS \
      "$DEV_IMAGE" \
      python3 -m unittest -v \
      tests/fusion_w1/test_fusion_w1_coreg_lock1.py
    ;;
  *)
    echo "usage: $0 {prepare-als|prepare-controls|measure|verify|test}" >&2
    exit 2
    ;;
esac
