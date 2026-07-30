#!/usr/bin/env bash
# Fusion W1 06:30 partial closeout wrapper. No stage command is exposed here.
set -Eeuo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CONFIG="phases/p2-gsjso/configs/fusion_w1/fusion_w1_partial_closeout_v1_20260726.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1/fusion_w1_partial_closeout_v1_20260726.py"
TEST="tests/fusion_w1/test_fusion_w1_partial_closeout_v1_20260726.py"

run_python() {
  docker compose run --rm --no-deps -T \
    --user "$(id -u):$(id -g)" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    dev python "$@"
}

case "${1:-}" in
  test)
    run_python "$TEST"
    ;;
  check)
    run_python "$SCRIPT" --config "$CONFIG" check
    ;;
  publish)
    run_python "$SCRIPT" --config "$CONFIG" publish
    ;;
  *)
    echo "usage: $0 {test|check|publish}" >&2
    exit 2
    ;;
esac
