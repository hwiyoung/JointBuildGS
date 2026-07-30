#!/usr/bin/env bash
# Docker-only publisher for dense qualitative v5.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

TOOLS_IMAGE="${DENSE_BASELINE_QUAL_IMAGE:-jointbuildgs-p0-tools:t0}"
TOOLS_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
ROOFER_IMAGE_ID="sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"
CONFIG="phases/p2-gsjso/configs/fusion_w1/fusion_w1_dense_baseline_qualitative_v5_20260728.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1/fusion_w1_dense_baseline_qualitative_v5_20260728.py"
TEST="tests/fusion_w1/test_fusion_w1_dense_baseline_qualitative_v5_20260728.py"
OUTPUT_REL="phases/p2-gsjso/runs/fusion_w1/20260728_fusion_w1_dense_baseline_qualitative_v5"
OUTPUT_PARENT_REL="phases/p2-gsjso/runs"
CONTAINER_REPO="/workspace/JointBuildGS"
ARTIFACT_HOST_ROOT="${JBGS_ARTIFACT_HOST_ROOT:-$REPO_ROOT/../JointBuildGS-artifacts}"
CONTAINER_ARTIFACT_ROOT="/artifacts/JointBuildGS"
HOST_FONT="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
CONTAINER_FONT="/opt/jointbuildgs-fonts/NotoSansCJK-Regular.ttc"
EXPECTED_FONT_SHA256="b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a"
EXPECTED_FONT_BYTES="19484784"
POINTCLOUD_REL="phases/p0-audit/data/work/w2/dim_v1_classified_z_minus0p174.laz"
FOOTPRINT_REL="phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg"
POINTCLOUD_HOST="$ARTIFACT_HOST_ROOT/phase-payloads/p0-audit/data/work/w2/dim_v1_classified_z_minus0p174.laz"
FOOTPRINT_HOST="$ARTIFACT_HOST_ROOT/phase-payloads/p0-audit/data/work/w2/footprints_scene_aoi.gpkg"
POINTCLOUD_CONTAINER="$CONTAINER_ARTIFACT_ROOT/phase-payloads/p0-audit/data/work/w2/dim_v1_classified_z_minus0p174.laz"
FOOTPRINT_CONTAINER="$CONTAINER_ARTIFACT_ROOT/phase-payloads/p0-audit/data/work/w2/footprints_scene_aoi.gpkg"

fail() {
  echo "dense baseline qualitative v5 wrapper error: $*" >&2
  exit 2
}

[[ -f "$CONFIG" ]] || fail "config absent: $CONFIG"
[[ -f "$SCRIPT" ]] || fail "renderer absent: $SCRIPT"
[[ -f "$TEST" ]] || fail "tests absent: $TEST"
[[ -f "$POINTCLOUD_HOST" ]] || fail "pointcloud absent: $POINTCLOUD_HOST"
[[ -f "$FOOTPRINT_HOST" ]] || fail "footprint absent: $FOOTPRINT_HOST"
[[ "$(docker image inspect "$TOOLS_IMAGE" --format '{{.Id}}')" == "$TOOLS_IMAGE_ID" ]] || fail "tools image ID mismatch"
[[ "$(docker image inspect "$ROOFER_IMAGE" --format '{{.Id}}')" == "$ROOFER_IMAGE_ID" ]] || fail "Roofer image ID mismatch"
[[ -f "$HOST_FONT" ]] || fail "required CJK font absent: $HOST_FONT"
[[ "$(sha256sum "$HOST_FONT" | awk '{print $1}')" == "$EXPECTED_FONT_SHA256" ]] || fail "CJK font hash mismatch"
[[ "$(stat -c '%s' "$HOST_FONT")" == "$EXPECTED_FONT_BYTES" ]] || fail "CJK font size mismatch"

docker_tools=(
  docker run --rm --pull=never --network=none --read-only
  --tmpfs /tmp:rw,nosuid,nodev,size=4g
  --memory=12g --memory-swap=12g --cpus=6 --pids-limit=1024 --shm-size=2g
  --security-opt=no-new-privileges:true --user "$(id -u):$(id -g)"
  --env MPLCONFIGDIR=/tmp/matplotlib --env XDG_CACHE_HOME=/tmp/cache
  --env PYTHONDONTWRITEBYTECODE=1 --env PYTHONHASHSEED=0
  --env DENSE_BASELINE_QUAL_FONT="$CONTAINER_FONT"
  --env JBGS_ARTIFACT_ROOT="$CONTAINER_ARTIFACT_ROOT"
  --volume "$REPO_ROOT:$CONTAINER_REPO:ro"
  --volume "$ARTIFACT_HOST_ROOT:$CONTAINER_ARTIFACT_ROOT:ro"
  --volume "$HOST_FONT:$CONTAINER_FONT:ro"
  --workdir "$CONTAINER_REPO" --entrypoint python3
)

run_tools_read_only() {
  "${docker_tools[@]}" "$TOOLS_IMAGE" "$@"
}

run_full_context_crop() {
  local crop_host="$1"
  docker run --rm --pull=never --network=none --read-only \
    --tmpfs /tmp:rw,nosuid,nodev,size=2g \
    --memory=24g --memory-swap=24g --cpus=8 --pids-limit=1024 --shm-size=2g \
    --security-opt=no-new-privileges:true --user "$(id -u):$(id -g)" \
    --volume "$REPO_ROOT:$CONTAINER_REPO:ro" \
    --volume "$ARTIFACT_HOST_ROOT:$CONTAINER_ARTIFACT_ROOT:ro" \
    --volume "$crop_host:/out:rw" \
    --workdir /out \
    "$ROOFER_IMAGE" \
    --id-attribute building_id \
    --box 690791.740 5335864.050 691154.650 5336353.850 \
    --crop-only --crop-output \
    "$POINTCLOUD_CONTAINER" \
    "$FOOTPRINT_CONTAINER" \
    /out/result \
    > "$crop_host/roofer.console.log" 2>&1
}

run_render() {
  local output_host="$REPO_ROOT/$OUTPUT_REL"
  local output_parent_host="$REPO_ROOT/$OUTPUT_PARENT_REL"
  local crop_host
  [[ ! -e "$output_host" ]] || fail "output exists; overwrite refused: $OUTPUT_REL"
  mkdir -p "$output_parent_host"
  crop_host="$(mktemp -d /tmp/jointbuildgs-dense-v5-crop.XXXXXX)"
  trap 'rm -rf -- "$crop_host"' RETURN
  run_full_context_crop "$crop_host"
  "${docker_tools[@]}" \
    --volume "$output_parent_host:$CONTAINER_REPO/$OUTPUT_PARENT_REL:rw" \
    --volume "$crop_host:/roofer-crop:ro" \
    "$TOOLS_IMAGE" "$SCRIPT" --config "$CONFIG" --crop-root /roofer-crop render
}

case "${1:-}" in
  check)
    [[ "$#" -eq 1 ]] || fail "usage: $0 check"
    run_tools_read_only "$SCRIPT" --config "$CONFIG" check
    ;;
  render)
    [[ "$#" -eq 1 ]] || fail "usage: $0 render"
    run_render
    ;;
  verify)
    [[ "$#" -eq 1 ]] || fail "usage: $0 verify"
    run_tools_read_only "$SCRIPT" --config "$CONFIG" verify
    ;;
  test)
    [[ "$#" -eq 1 ]] || fail "usage: $0 test"
    run_tools_read_only -c 'import laspy, lxml, matplotlib, numpy, PIL, shapely; print("deps=ok")'
    run_tools_read_only -m unittest -v "$TEST"
    ;;
  *) fail "usage: $0 {check|render|verify|test}" ;;
esac
