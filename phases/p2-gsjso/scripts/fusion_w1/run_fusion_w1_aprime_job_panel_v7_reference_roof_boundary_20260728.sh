#!/usr/bin/env bash
# Docker-only publisher for A-prime r1 panel-v7 reference roof boundaries.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

IMAGE="${APRIME_JOB_PANEL_IMAGE:-jointbuildgs:dev}"
EXPECTED_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
CONFIG="phases/p2-gsjso/configs/fusion_w1/fusion_w1_aprime_job_panel_v7_reference_roof_boundary_20260728.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1/fusion_w1_aprime_job_panel_v7_reference_roof_boundary_20260728.py"
TEST="tests/fusion_w1/test_fusion_w1_aprime_job_panel_v7_reference_roof_boundary_20260728.py"
OUTPUT_REL="phases/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/review_v7_reference_roof_boundary"
CONTAINER_REPO="/workspace/JointBuildGS"
ARTIFACT_HOST_ROOT="${JBGS_ARTIFACT_HOST_ROOT:-$REPO_ROOT/../JointBuildGS-artifacts}"
CONTAINER_ARTIFACT_ROOT="/artifacts/JointBuildGS"
OUTPUT_ARTIFACT_REL="phase-payloads/p2-gsjso/runs/fusion_w1/20260726_fusion_w1_aprime/review_v7_reference_roof_boundary"
HOST_FONT="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
CONTAINER_FONT="/opt/jointbuildgs-fonts/NotoSansCJK-Regular.ttc"
EXPECTED_FONT_SHA256="b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a"
EXPECTED_FONT_BYTES="19484784"

fail() {
  echo "job panel v7 reference-roof wrapper error: $*" >&2
  exit 2
}

command="${1:-}"
case "$command" in
  test|check-all|backfill-all|verify-all)
    [[ "$#" -eq 1 ]] || fail "usage: $0 {$command}"
    ;;
  check-one|backfill-one|verify-one)
    [[ "$#" -eq 2 ]] || fail "usage: $0 {$command} DEBY_LOD2_<id>"
    [[ "$2" =~ ^DEBY_LOD2_[0-9]+$ ]] || fail "invalid building ID: $2"
    ;;
  *)
    fail "usage: $0 {test|check-one|backfill-one|verify-one|check-all|backfill-all|verify-all} [DEBY_LOD2_<id>]"
    ;;
esac

observed_image_id="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
[[ "$observed_image_id" == "$EXPECTED_IMAGE_ID" ]] || fail "image ID mismatch: $observed_image_id"
[[ -d "$ARTIFACT_HOST_ROOT" ]] || fail "artifact root absent: $ARTIFACT_HOST_ROOT"
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
  --memory=16g
  --memory-swap=16g
  --cpus=6
  --shm-size=2g
  --user "$(id -u):$(id -g)"
  --env MPLCONFIGDIR=/tmp/matplotlib
  --env XDG_CACHE_HOME=/tmp/cache
  --env PYTHONDONTWRITEBYTECODE=1
  --env PYTHONHASHSEED=0
  --env APRIME_JOB_QUALITATIVE_FONT="$CONTAINER_FONT"
  --env JBGS_ARTIFACT_ROOT="$CONTAINER_ARTIFACT_ROOT"
  --volume "$REPO_ROOT:$CONTAINER_REPO:ro"
  --volume "$ARTIFACT_HOST_ROOT:$CONTAINER_ARTIFACT_ROOT:ro"
  --volume "$HOST_FONT:$CONTAINER_FONT:ro"
  --workdir "$CONTAINER_REPO"
  --entrypoint python3
)

if [[ "$command" == "test" ]]; then
  "${docker_base[@]}" "$IMAGE" -m unittest -v "$TEST"
  exit 0
fi

args=("$SCRIPT" --config "$CONFIG")
if [[ "$command" == "backfill-one" || "$command" == "backfill-all" ]]; then
  output_host="$ARTIFACT_HOST_ROOT/$OUTPUT_ARTIFACT_REL"
  mkdir -p "$output_host"
  docker_base+=(--volume "$output_host:$CONTAINER_REPO/$OUTPUT_REL:rw")
fi
args+=("$command")
if [[ "$command" == *-one ]]; then
  args+=("$2")
fi
"${docker_base[@]}" "$IMAGE" "${args[@]}"
