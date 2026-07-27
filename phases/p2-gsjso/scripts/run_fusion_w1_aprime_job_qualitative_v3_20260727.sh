#!/usr/bin/env bash
# Docker-only CPU renderer for one measured A-prime qualitative review bundle.
set -Eeuo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

IMAGE="${APRIME_JOB_QUALITATIVE_IMAGE:-jointbuildgs:dev}"
EXPECTED_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
CONFIG="phases/p2-gsjso/configs/fusion_w1_aprime_job_qualitative_v3_20260727.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1_aprime_job_qualitative_v3_20260727.py"
TEST="phases/p2-gsjso/scripts/test_fusion_w1_aprime_job_qualitative_v3_20260727.py"
OUTPUT_REL="phases/p2-gsjso/runs/20260726_fusion_w1_aprime/review_v3"
CONTAINER_REPO="/workspace/JointBuildGS"
HOST_FONT="/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
CONTAINER_FONT="/opt/jointbuildgs-fonts/NotoSansCJK-Regular.ttc"
EXPECTED_FONT_SHA256="b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a"
EXPECTED_FONT_BYTES="19484784"

fail() {
  echo "job qualitative wrapper error: $*" >&2
  exit 2
}

validate_identity_args() {
  local building_id="$1"
  local arm="$2"
  local replicate="$3"
  [[ "$building_id" =~ ^DEBY_LOD2_[0-9]+$ ]] || fail "invalid building_id: $building_id"
  [[ "$arm" == "Aprime" || "$arm" == "B" ]] || fail "invalid arm: $arm"
  [[ "$replicate" == "r1" || "$replicate" == "r2" ]] || fail "invalid replicate: $replicate"
}

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
  --tmpfs /tmp:rw,nosuid,nodev,size=3g
  --memory=12g
  --memory-swap=12g
  --cpus=6
  --shm-size=2g
  --user "$(id -u):$(id -g)"
  --env HOME=/tmp/home
  --env MPLCONFIGDIR=/tmp/matplotlib
  --env XDG_CACHE_HOME=/tmp/cache
  --env PYTHONDONTWRITEBYTECODE=1
  --env PYTHONHASHSEED=0
  --env APRIME_JOB_QUALITATIVE_FONT="$CONTAINER_FONT"
  --volume "$REPO_ROOT:$CONTAINER_REPO:ro"
  --volume "$HOST_FONT:$CONTAINER_FONT:ro"
  --workdir "$CONTAINER_REPO"
  --entrypoint python3
)

run_read_only() {
  "${docker_base[@]}" "$IMAGE" "$@"
}

run_one() {
  local building_id="$1"
  local arm="$2"
  local replicate="$3"
  local output_host="$REPO_ROOT/$OUTPUT_REL"
  mkdir -p "$output_host"
  "${docker_base[@]}" \
    --volume "$output_host:$CONTAINER_REPO/$OUTPUT_REL:rw" \
    "$IMAGE" "$SCRIPT" --config "$CONFIG" one "$building_id" "$arm" "$replicate"
}

run_temp_smoke() {
  local temporary
  temporary="$(mktemp -d --tmpdir jointbuildgs-aprime-review-v3.XXXXXX)"
  cleanup_temp() {
    if [[ -n "${temporary:-}" && "$temporary" == /tmp/jointbuildgs-aprime-review-v3.* ]]; then
      rm -rf -- "$temporary"
    fi
  }
  trap cleanup_temp RETURN
  "${docker_base[@]}" \
    --volume "$temporary:/tmp/review-v3-output:rw" \
    "$IMAGE" "$SCRIPT" --config "$CONFIG" --output-root /tmp/review-v3-output \
    one DEBY_LOD2_42364609 Aprime r1
}

case "${1:-}" in
  one)
    [[ "$#" -eq 4 ]] || fail "usage: $0 one <building_id> <arm> <replicate>"
    validate_identity_args "$2" "$3" "$4"
    run_one "$2" "$3" "$4"
    ;;
  check)
    [[ "$#" -eq 4 ]] || fail "usage: $0 check <building_id> <arm> <replicate>"
    validate_identity_args "$2" "$3" "$4"
    run_read_only "$SCRIPT" --config "$CONFIG" check "$2" "$3" "$4"
    ;;
  verify)
    [[ "$#" -eq 4 ]] || fail "usage: $0 verify <building_id> <arm> <replicate>"
    validate_identity_args "$2" "$3" "$4"
    run_read_only "$SCRIPT" --config "$CONFIG" verify "$2" "$3" "$4"
    ;;
  test)
    [[ "$#" -eq 1 ]] || fail "usage: $0 test"
    run_read_only -m unittest -v "$TEST"
    ;;
  smoke-temp)
    [[ "$#" -eq 1 ]] || fail "usage: $0 smoke-temp"
    run_temp_smoke
    ;;
  *)
    fail "usage: $0 {one|check|verify|test|smoke-temp} [building_id arm replicate]"
    ;;
esac
