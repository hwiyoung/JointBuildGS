#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
CONTAINER_ROOT="/workspace/JointBuildGS"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
EXPECTED_TOOLS_IMAGE_ID="sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0"
TRAINING_LAUNCHER="${SCRIPT_DIR}/run_e5_c001_s3ap_phase2.sh"
ARCHIVER="phases/p2-gsjso/scripts/e5_c001_s3ap_phase2_archive_base42.py"

ACTUAL_TOOLS_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${TOOLS_IMAGE}")"
if [[ "${ACTUAL_TOOLS_IMAGE_ID}" != "${EXPECTED_TOOLS_IMAGE_ID}" ]]; then
  echo "locked archive tools image mismatch: ${ACTUAL_TOOLS_IMAGE_ID} != ${EXPECTED_TOOLS_IMAGE_ID}" >&2
  exit 2
fi

# Capture the locked training-image runner's checkpoint-semantic audit in
# memory. The pinned NGC image writes its license banner to stdout before the
# runner's one-line JSON, so isolate the final non-empty line and fail closed
# if any earlier line could itself be another JSON object. No temporary or
# redirected attestation file is created.
RUNNER_DRY_RUN_OUTPUT="$("${TRAINING_LAUNCHER}" run --dry-run)"
if [[ -z "${RUNNER_DRY_RUN_OUTPUT}" ]]; then
  echo "locked runner dry-run returned empty attestation" >&2
  exit 2
fi
RUNNER_DRY_RUN_JSON="${RUNNER_DRY_RUN_OUTPUT##*$'\n'}"
RUNNER_DRY_RUN_PREFIX="${RUNNER_DRY_RUN_OUTPUT%$'\n'*}"
if [[ "${RUNNER_DRY_RUN_JSON}" != \{*\} ]]; then
  echo "locked runner dry-run final stdout line is not a JSON object" >&2
  exit 2
fi
if [[ "${RUNNER_DRY_RUN_OUTPUT}" != "${RUNNER_DRY_RUN_JSON}" ]] && \
   [[ "${RUNNER_DRY_RUN_PREFIX}" == *'{'* || "${RUNNER_DRY_RUN_PREFIX}" == *'}'* ]]; then
  echo "locked runner dry-run emitted ambiguous JSON-like stdout before attestation" >&2
  exit 2
fi

exec docker run --rm --user "$(id -u):$(id -g)" -v "${REPO_ROOT}:${CONTAINER_ROOT}" -w "${CONTAINER_ROOT}" "${ACTUAL_TOOLS_IMAGE_ID}" python "${ARCHIVER}" "$@" --runner-dry-run-attestation-json "${RUNNER_DRY_RUN_JSON}" --tools-image-id "${ACTUAL_TOOLS_IMAGE_ID}"
