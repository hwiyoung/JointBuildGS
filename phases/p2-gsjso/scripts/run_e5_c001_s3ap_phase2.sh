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
MODE="${1:-run}"
if [[ $# -gt 0 ]]; then
  shift
fi

COMMON=(
  --rm
  --user "${HOST_UID}:${HOST_GID}"
  -e "S3AP_DOCKER_IMAGE_ID=${ACTUAL_IMAGE_ID}"
  -e "S3AP_HOST_UID=${HOST_UID}"
  -e "S3AP_HOST_GID=${HOST_GID}"
  -v "${REPO_ROOT}:${CONTAINER_ROOT}"
  -w "${CONTAINER_ROOT}"
)

case "${MODE}" in
  prepare)
    exec docker run "${COMMON[@]}" "${IMAGE}" \
      python phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_prepare.py "$@"
    ;;
  run)
    exec docker run "${COMMON[@]}" --gpus all "${IMAGE}" \
      python phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_runner.py "$@"
    ;;
  *)
    echo "usage: $0 {prepare|run} [arguments...]" >&2
    exit 2
    ;;
esac
