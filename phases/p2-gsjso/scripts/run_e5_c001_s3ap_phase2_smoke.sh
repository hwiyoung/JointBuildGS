#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
IMAGE="jointbuildgs:dev"
EXPECTED_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
CONTAINER_ROOT="/workspace/JointBuildGS"

ACTUAL_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${IMAGE}")"
if [[ "${ACTUAL_IMAGE_ID}" != "${EXPECTED_IMAGE_ID}" ]]; then
  echo "locked image mismatch: ${ACTUAL_IMAGE_ID} != ${EXPECTED_IMAGE_ID}" >&2
  exit 2
fi

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
RUNTIME_ROOT="${REPO_ROOT}/results/tum_transfer/e5_s3ap_phase2/runtime"
mkdir -p "${RUNTIME_ROOT}/home" "${RUNTIME_ROOT}/xdg_cache" "${RUNTIME_ROOT}/torch_extensions"
MODE="${1:-plan}"
if [[ $# -gt 0 ]]; then
  shift
fi

COMMON=(
  --rm
  --user "${HOST_UID}:${HOST_GID}"
  -e "S3AP_SMOKE_DOCKER_IMAGE_ID=${ACTUAL_IMAGE_ID}"
  -e "S3AP_SMOKE_HOST_UID=${HOST_UID}"
  -e "S3AP_SMOKE_HOST_GID=${HOST_GID}"
  -e "HOME=${CONTAINER_ROOT}/results/tum_transfer/e5_s3ap_phase2/runtime/home"
  -e "XDG_CACHE_HOME=${CONTAINER_ROOT}/results/tum_transfer/e5_s3ap_phase2/runtime/xdg_cache"
  -e "TORCH_EXTENSIONS_DIR=${CONTAINER_ROOT}/results/tum_transfer/e5_s3ap_phase2/runtime/torch_extensions"
  -v "${REPO_ROOT}:${CONTAINER_ROOT}"
  -w "${CONTAINER_ROOT}"
)

case "${MODE}" in
  plan)
    exec docker run "${COMMON[@]}" "${IMAGE}" \
      python phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_smoke.py \
      --prepare-only "$@"
    ;;
  run)
    exec docker run "${COMMON[@]}" --gpus all "${IMAGE}" \
      python phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_smoke.py "$@"
    ;;
  test)
    exec docker run "${COMMON[@]}" "${IMAGE}" \
      python phases/p2-gsjso/scripts/test_e5_c001_s3ap_phase2_smoke.py "$@"
    ;;
  *)
    echo "usage: $0 {plan|run|test} [arguments...]" >&2
    exit 2
    ;;
esac
