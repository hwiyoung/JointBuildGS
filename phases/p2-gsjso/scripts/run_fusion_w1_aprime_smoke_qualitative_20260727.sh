#!/usr/bin/env bash
# Docker-only, non-networked publication of the recovered smoke qualitative panel.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

IMAGE="${APRIME_SMOKE_QUALITATIVE_IMAGE:-jointbuildgs:dev}"
EXPECTED_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
CONFIG="phases/p2-gsjso/configs/fusion_w1_aprime_smoke_qualitative_20260727.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1_aprime_smoke_qualitative_20260727.py"
TEST="phases/p2-gsjso/scripts/test_fusion_w1_aprime_smoke_qualitative_20260727.py"
OUTPUT_REL="phases/p2-gsjso/runs/20260727_fusion_w1_aprime_smoke_recovery/qualitative_smoke"
CONTAINER_REPO="/workspace/JointBuildGS"
GIT_COMMON_DIR="$(git rev-parse --path-format=absolute --git-common-dir)"
GIT_MOUNTS=()
if [[ "$GIT_COMMON_DIR" != "$REPO_ROOT/.git" ]]; then
  GIT_MOUNTS=(--volume "$GIT_COMMON_DIR:$GIT_COMMON_DIR:ro")
fi

observed_image_id="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
if [[ "$observed_image_id" != "$EXPECTED_IMAGE_ID" ]]; then
  echo "qualitative image ID mismatch: $observed_image_id" >&2
  exit 2
fi

docker_base=(
  docker run --rm
  --pull=never
  --network=none
  --read-only
  --tmpfs /tmp:rw,nosuid,nodev,size=2g
  --memory=12g
  --memory-swap=12g
  --cpus=6
  --shm-size=2g
  --user "$(id -u):$(id -g)"
  --env MPLCONFIGDIR=/tmp/matplotlib
  --env XDG_CACHE_HOME=/tmp/cache
  --env PYTHONDONTWRITEBYTECODE=1
  --env PYTHONHASHSEED=0
  --volume "$REPO_ROOT:$CONTAINER_REPO:ro"
  "${GIT_MOUNTS[@]}"
  --workdir "$CONTAINER_REPO"
  --entrypoint python3
)

run_read_only() {
  "${docker_base[@]}" "$IMAGE" "$@"
}

run_with_output() {
  local output_host="$REPO_ROOT/$OUTPUT_REL"
  mkdir -p "$output_host"
  "${docker_base[@]}" \
    --volume "$output_host:$CONTAINER_REPO/$OUTPUT_REL:rw" \
    "$IMAGE" "$@"
}

case "${1:-}" in
  test)
    run_read_only -m unittest -v "$TEST"
    ;;
  check)
    run_read_only "$SCRIPT" --config "$CONFIG" check
    ;;
  build)
    run_with_output "$SCRIPT" --config "$CONFIG" build
    ;;
  verify)
    run_read_only "$SCRIPT" --config "$CONFIG" verify
    ;;
  strict-check)
    run_read_only "$SCRIPT" --config "$CONFIG" strict-check
    ;;
  publish-strict)
    run_with_output "$SCRIPT" --config "$CONFIG" publish-strict
    ;;
  verify-strict)
    run_read_only "$SCRIPT" --config "$CONFIG" verify-strict
    ;;
  *)
    echo "usage: $0 {test|check|build|verify|strict-check|publish-strict|verify-strict}" >&2
    exit 2
    ;;
esac
