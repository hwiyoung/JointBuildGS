#!/usr/bin/env bash
# Docker-only CPU wrapper for the corrected P0 raw-dense qualitative bundle.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

IMAGE="${DENSE_BASELINE_QUAL_IMAGE:-jointbuildgs-p0-tools:t0}"
EXPECTED_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
CONFIG="phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v2_20260728.py"
TEST="tests/fusion_w1/test_fusion_w1_dense_baseline_qualitative_v2_20260728.py"
OUTPUT_REL="phases/p2-gsjso/runs/20260728_fusion_w1_dense_baseline_qualitative_v2"
OUTPUT_PARENT_REL="phases/p2-gsjso/runs"
CONTAINER_REPO="/workspace/JointBuildGS"
ARTIFACT_HOST_ROOT="${JBGS_ARTIFACT_HOST_ROOT:-$REPO_ROOT/../JointBuildGS-artifacts}"
CONTAINER_ARTIFACT_ROOT="/artifacts/JointBuildGS"
HOST_FONT="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
CONTAINER_FONT="/opt/jointbuildgs-fonts/NotoSansCJK-Regular.ttc"
EXPECTED_FONT_SHA256="b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a"
EXPECTED_FONT_BYTES="19484784"

fail() {
  echo "dense baseline qualitative v2 wrapper error: $*" >&2
  exit 2
}

[[ -f "$CONFIG" ]] || fail "config absent: $CONFIG"
[[ -f "$SCRIPT" ]] || fail "renderer absent: $SCRIPT"
[[ -f "$TEST" ]] || fail "tests absent: $TEST"
[[ -d "$ARTIFACT_HOST_ROOT" ]] || fail "artifact root absent: $ARTIFACT_HOST_ROOT"
observed_image_id="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
[[ "$observed_image_id" == "$EXPECTED_IMAGE_ID" ]] \
  || fail "image ID mismatch: $observed_image_id"
[[ -f "$HOST_FONT" ]] || fail "required CJK font absent: $HOST_FONT"
observed_font_sha256="$(sha256sum "$HOST_FONT" | awk '{print $1}')"
observed_font_bytes="$(stat -c '%s' "$HOST_FONT")"
[[ "$observed_font_sha256" == "$EXPECTED_FONT_SHA256" ]] || fail "CJK font hash mismatch"
[[ "$observed_font_bytes" == "$EXPECTED_FONT_BYTES" ]] || fail "CJK font size mismatch"

docker_base=(
  docker run --rm
  --pull=never
  --network=none
  --read-only
  --tmpfs /tmp:rw,nosuid,nodev,size=4g
  --memory=12g
  --memory-swap=12g
  --cpus=6
  --pids-limit=1024
  --shm-size=2g
  --security-opt=no-new-privileges:true
  --user "$(id -u):$(id -g)"
  --env MPLCONFIGDIR=/tmp/matplotlib
  --env XDG_CACHE_HOME=/tmp/cache
  --env PYTHONDONTWRITEBYTECODE=1
  --env PYTHONHASHSEED=0
  --env DENSE_BASELINE_QUAL_FONT="$CONTAINER_FONT"
  --env JBGS_ARTIFACT_ROOT="$CONTAINER_ARTIFACT_ROOT"
  --volume "$REPO_ROOT:$CONTAINER_REPO:ro"
  --volume "$ARTIFACT_HOST_ROOT:$CONTAINER_ARTIFACT_ROOT:ro"
  --volume "$HOST_FONT:$CONTAINER_FONT:ro"
  --workdir "$CONTAINER_REPO"
  --entrypoint python3
)

run_read_only() {
  "${docker_base[@]}" "$IMAGE" "$@"
}

run_render() {
  local output_host="$REPO_ROOT/$OUTPUT_REL"
  local output_parent_host="$REPO_ROOT/$OUTPUT_PARENT_REL"
  [[ ! -e "$output_host" ]] || fail "output exists; overwrite refused: $OUTPUT_REL"
  mkdir -p "$output_parent_host"
  "${docker_base[@]}" \
    --volume "$output_parent_host:$CONTAINER_REPO/$OUTPUT_PARENT_REL:rw" \
    "$IMAGE" "$SCRIPT" --config "$CONFIG" render
}

dependency_smoke() {
  run_read_only -c \
    'import laspy, lxml, matplotlib, numpy, PIL, shapely; from src.stage2 import image_projection; print("deps=projection,laspy,lxml,matplotlib,numpy,PIL,shapely:ok")'
}

case "${1:-}" in
  check)
    [[ "$#" -eq 1 ]] || fail "usage: $0 check"
    run_read_only "$SCRIPT" --config "$CONFIG" check
    ;;
  render)
    [[ "$#" -eq 1 ]] || fail "usage: $0 render"
    run_render
    ;;
  verify)
    [[ "$#" -eq 1 ]] || fail "usage: $0 verify"
    run_read_only "$SCRIPT" --config "$CONFIG" verify
    ;;
  test)
    [[ "$#" -eq 1 ]] || fail "usage: $0 test"
    dependency_smoke
    run_read_only -m unittest -v "$TEST"
    ;;
  *)
    fail "usage: $0 {check|render|verify|test}"
    ;;
esac
