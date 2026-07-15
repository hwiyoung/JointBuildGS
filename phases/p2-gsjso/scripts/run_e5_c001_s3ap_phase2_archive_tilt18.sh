#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
CONTAINER_ROOT="/workspace/JointBuildGS"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
EXPECTED_TOOLS_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
TRAINING_LAUNCHER="${SCRIPT_DIR}/run_e5_c001_s3ap_phase2.sh"
TILT_INVENTORY="phases/p2-gsjso/runs/20260715_e5_c001_s3ap_phase2_prepare/tilt_jobs.csv"
ARCHIVER="phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_archive_tilt18.py"

ACTUAL_TOOLS_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${TOOLS_IMAGE}")"
if [[ "${ACTUAL_TOOLS_IMAGE_ID}" != "${EXPECTED_TOOLS_IMAGE_ID}" ]]; then
  echo "locked archive tools image mismatch: ${ACTUAL_TOOLS_IMAGE_ID} != ${EXPECTED_TOOLS_IMAGE_ID}" >&2
  exit 2
fi

# Capture the locked training-image runner's exact tilt checkpoint audit in
# memory.  The runner validates tilt_manifest.json and every final.pt; neither
# status.csv nor an intermediate attestation file is written by --dry-run.
RUNNER_DRY_RUN_JSON="$("${TRAINING_LAUNCHER}" run --inventory "${TILT_INVENTORY}" --dry-run)"
if [[ -z "${RUNNER_DRY_RUN_JSON}" ]]; then
  echo "locked tilt runner dry-run returned empty attestation" >&2
  exit 2
fi

exec docker run --rm --user "$(id -u):$(id -g)" \
  -v "${REPO_ROOT}:${CONTAINER_ROOT}" -w "${CONTAINER_ROOT}" \
  "${ACTUAL_TOOLS_IMAGE_ID}" python "${ARCHIVER}" "$@" \
  --runner-dry-run-attestation-json "${RUNNER_DRY_RUN_JSON}" \
  --tools-image-id "${ACTUAL_TOOLS_IMAGE_ID}"
