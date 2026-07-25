#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
CONFIG="phases/p2-gsjso/configs/fusion_w1_coregdiag_20260725.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1_coregdiag_20260725.py"
TEST="phases/p2-gsjso/scripts/test_fusion_w1_coregdiag_20260725.py"
DEV_IMAGE="jointbuildgs:dev"
DEV_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
MEMORY="24g"

observed="$(docker image inspect "$DEV_IMAGE" --format '{{.Id}}')"
if [[ "$observed" != "$DEV_IMAGE_ID" ]]; then
  echo "[BLOCKED] image ID mismatch: $observed" >&2
  exit 2
fi

host_learning="$(
  ps -eo pid=,args= |
    awk '
      BEGIN { IGNORECASE=1 }
      /train[.]py|p1w_train|gs_train|gaussian[_-]splatting\/train|full_eval[.]py/ &&
      $0 !~ /awk/ { print }
    '
)"
container_learning="$(
  docker ps --format '{{.ID}} {{.Image}} {{.Command}} {{.Names}}' |
    awk '
      BEGIN { IGNORECASE=1 }
      /train[.]py|p1w_train|gs_train|gaussian[_-]splatting\/train|full_eval[.]py/ { print }
    '
)"
if [[ -n "$host_learning" || -n "$container_learning" ]]; then
  echo "[BLOCKED] concurrent learning-like process detected" >&2
  [[ -n "$host_learning" ]] && echo "$host_learning" >&2
  [[ -n "$container_learning" ]] && echo "$container_learning" >&2
  exit 2
fi

run_python() {
  docker run --rm \
    --pull=never \
    --network=none \
    --pid=host \
    --memory="$MEMORY" \
    --memory-swap="$MEMORY" \
    --shm-size=8g \
    --cap-drop=ALL \
    --security-opt=no-new-privileges \
    --user "$(id -u):$(id -g)" \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --env PYTHONUNBUFFERED=1 \
    --env MPLCONFIGDIR=/tmp/matplotlib \
    --env XDG_CACHE_HOME=/tmp/cache \
    --env CUDA_VISIBLE_DEVICES= \
    --env NVIDIA_VISIBLE_DEVICES=void \
    --tmpfs /tmp:rw,nosuid,nodev,size=4g,mode=1777 \
    --volume "$ROOT:/workspace/JointBuildGS:rw" \
    --workdir /workspace/JointBuildGS \
    "$DEV_IMAGE" \
    python3 "$@"
}

case "${1:-}" in
  test)
    run_python -m unittest -v "$TEST"
    ;;
  lock)
    run_python "$SCRIPT" --config "$CONFIG" lock
    ;;
  measure)
    run_python "$SCRIPT" --config "$CONFIG" measure
    ;;
  recover-publish)
    run_python "$SCRIPT" --config "$CONFIG" recover-publish
    ;;
  verify)
    run_python "$SCRIPT" --config "$CONFIG" verify
    ;;
  *)
    echo "usage: $0 {test|lock|measure|recover-publish|verify}" >&2
    exit 2
    ;;
esac
