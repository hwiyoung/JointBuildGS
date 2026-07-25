#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
IMAGE="jointbuildgs:dev"
IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
GPU_DEVICE="${FUS_W1_GPU_DEVICE:-1}"
CONFIG="phases/p2-gsjso/configs/fusion_w1_resume_r0_v2_20260725.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1_resume_r0_v2_20260725.py"
TEST="phases/p2-gsjso/scripts/test_fusion_w1_resume_r0_v2_20260725.py"

observed="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
if [[ "$observed" != "$IMAGE_ID" ]]; then
  echo "image ID mismatch: $observed" >&2
  exit 2
fi

run_python() {
  docker run --rm \
    --pull=never \
    --gpus "device=${GPU_DEVICE}" \
    --pid=host \
    --memory=24g \
    --memory-swap=24g \
    --shm-size=8g \
    --user "$(id -u):$(id -g)" \
    --group-add "$(stat -c '%g' /var/run/docker.sock)" \
    --env PYTHONDONTWRITEBYTECODE=1 \
    --env FUS_W1_HOST_REPO="$ROOT" \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    --volume /usr/bin/docker:/usr/local/bin/docker:ro \
    --volume "$ROOT:/workspace/JointBuildGS" \
    --volume "$ROOT:/host-control/JointBuildGS:ro" \
    --workdir /workspace/JointBuildGS \
    --entrypoint python3 \
    "$IMAGE" "$@"
}

case "${1:-}" in
  preflight)
    run_python "$SCRIPT" --config "$CONFIG"
    ;;
  test)
    run_python -m unittest -v "$TEST"
    ;;
  *)
    echo "usage: $0 {preflight|test}" >&2
    exit 2
    ;;
esac
