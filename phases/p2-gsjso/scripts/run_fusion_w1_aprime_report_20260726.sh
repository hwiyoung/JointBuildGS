#!/usr/bin/env bash
# Docker-only observational aggregation and panel generator for arm A-prime.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

IMAGE="${APRIME_REPORT_IMAGE:-jointbuildgs:dev}"
EXPECTED_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
CONFIG="phases/p2-gsjso/configs/fusion_w1_aprime_report_20260726.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1_aprime_report_20260726.py"
TEST="phases/p2-gsjso/scripts/test_fusion_w1_aprime_report_20260726.py"

observed_image_id="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
if [[ "$observed_image_id" != "$EXPECTED_IMAGE_ID" ]]; then
  echo "report image ID mismatch: $observed_image_id" >&2
  exit 2
fi

run_python() {
  docker run --rm \
    --pull=never \
    --network=none \
    --memory=12g \
    --memory-swap=12g \
    --cpus=6 \
    --shm-size=2g \
    --user "$(id -u):$(id -g)" \
    --env MPLCONFIGDIR=/tmp/matplotlib \
    --env XDG_CACHE_HOME=/tmp/cache \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --volume "$REPO_ROOT:/workspace/JointBuildGS" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$IMAGE" "$@"
}

case "${1:-}" in
  test)
    run_python -m unittest -v "$TEST"
    ;;
  check)
    run_python "$SCRIPT" --config "$CONFIG" check
    ;;
  partial)
    run_python "$SCRIPT" --config "$CONFIG" build
    ;;
  final)
    run_python "$SCRIPT" --config "$CONFIG" build --require-terminal
    ;;
  *)
    echo "usage: $0 {test|check|partial|final}" >&2
    exit 2
    ;;
esac
