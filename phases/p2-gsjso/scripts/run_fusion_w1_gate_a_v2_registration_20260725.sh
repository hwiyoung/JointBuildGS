#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
IMAGE="jointbuildgs-p0-tools:t0"
IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
CONFIG="phases/p2-gsjso/configs/fusion_w1_gate_a_v2_registration_20260725.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1_gate_a_v2_registration_20260725.py"
TEST="phases/p2-gsjso/scripts/test_fusion_w1_gate_a_v2_registration_20260725.py"

observed="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
if [[ "$observed" != "$IMAGE_ID" ]]; then
  echo "image ID mismatch: $observed" >&2
  exit 2
fi

run_python() {
  docker run --rm \
    --pull=never \
    --network=none \
    --memory=24g \
    --memory-swap=24g \
    --shm-size=4g \
    --user "$(id -u):$(id -g)" \
    --env HOME=/tmp \
    --env MPLCONFIGDIR=/tmp/matplotlib \
    --env XDG_CACHE_HOME=/tmp \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --volume "$ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$IMAGE" "$@"
}

case "${1:-}" in
  publish)
    run_python "$SCRIPT" --config "$CONFIG" publish
    ;;
  test)
    run_python -m unittest -v "$TEST"
    ;;
  *)
    echo "usage: $0 {publish|test}" >&2
    exit 2
    ;;
esac
