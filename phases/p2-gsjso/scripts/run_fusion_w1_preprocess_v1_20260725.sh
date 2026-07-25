#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
IMAGE="jointbuildgs-p0-tools:t0"
EXPECTED_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
CONFIG="phases/p2-gsjso/configs/fusion_w1_preprocess_v1_20260725.json"
SCRIPT="phases/p2-gsjso/scripts/fusion_w1_preprocess_v1_20260725.py"
TEST_SCRIPT="phases/p2-gsjso/scripts/test_fusion_w1_preprocess_v1_20260725.py"

MODE="${1:-}"
if [[ -z "${MODE}" ]]; then
  echo "usage: $0 test | one <building-id> | all-core" >&2
  exit 64
fi

OBSERVED_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${IMAGE}")"
if [[ "${OBSERVED_IMAGE_ID}" != "${EXPECTED_IMAGE_ID}" ]]; then
  echo "BLOCKED: ${IMAGE} id ${OBSERVED_IMAGE_ID} != ${EXPECTED_IMAGE_ID}" >&2
  exit 2
fi

COMMON=(
  docker run --rm --pull=never --network=none
  --user "$(id -u):$(id -g)"
  --env PYTHONDONTWRITEBYTECODE=1
  --env PYTHONUTF8=1
  --env MPLCONFIGDIR=/tmp/matplotlib
  --env XDG_CACHE_HOME=/tmp
  --tmpfs /tmp:rw,nosuid,nodev,size=2g
  --workdir /workspace/JointBuildGS
)

case "${MODE}" in
  test)
    "${COMMON[@]}" \
      --read-only \
      --memory=4g --cpus=4 \
      --volume "${REPO_ROOT}:/workspace/JointBuildGS:ro" \
      "${IMAGE}" \
      python "${TEST_SCRIPT}"
    ;;
  one)
    BUILDING_ID="${2:-}"
    if [[ -z "${BUILDING_ID}" ]]; then
      echo "usage: $0 one <building-id>" >&2
      exit 64
    fi
    "${COMMON[@]}" \
      --memory=24g --cpus=12 \
      --volume "${REPO_ROOT}:/workspace/JointBuildGS:rw" \
      "${IMAGE}" \
      python "${SCRIPT}" --config "${CONFIG}" --building-id "${BUILDING_ID}"
    ;;
  all-core)
    "${COMMON[@]}" \
      --memory=24g --cpus=12 \
      --volume "${REPO_ROOT}:/workspace/JointBuildGS:rw" \
      "${IMAGE}" \
      python "${SCRIPT}" --config "${CONFIG}" --all-core
    ;;
  *)
    echo "usage: $0 test | one <building-id> | all-core" >&2
    exit 64
    ;;
esac
