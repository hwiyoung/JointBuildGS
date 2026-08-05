#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CONFIG_PATH="${DENSE_SCENE_CONFIG_PATH:-${REPO_ROOT}/configs/p2/mvs_native_textured_mesh_preflight_v1/dense_scene_recovery.env}"

# shellcheck source=/dev/null
source "${CONFIG_PATH}"

ARTIFACT_ROOT="${JBGS_ARTIFACT_HOST_ROOT:-${REPO_ROOT}/../JointBuildGS-artifacts}"
ARTIFACT_ROOT="$(cd "${ARTIFACT_ROOT}" && pwd)"
SOURCE_SCENE="${ARTIFACT_ROOT}/${SOURCE_SCENE_REL}"
SOURCE_DENSE_PLY="${ARTIFACT_ROOT}/${SOURCE_DENSE_PLY_REL}"
SOURCE_IMAGES="${ARTIFACT_ROOT}/${SOURCE_IMAGES_REL}"
SOURCE_DATA="${ARTIFACT_ROOT}/${SOURCE_DATA_REL}"
RUN_ROOT="${ARTIFACT_ROOT}/${OUTPUT_REL}"
WORK_OPENMVS="${RUN_ROOT}/work/mvs/openmvs"
WORK_IMAGES="${RUN_ROOT}/work/mvs/colmap_dense/images"
LOG_PATH="${RUN_ROOT}/densify_point_cloud.log"
RECEIPT_PATH="${RUN_ROOT}/run_receipt.env"
COMPARISON_PATH="${RUN_ROOT}/dense_ply_comparison.env"

require_file() {
  local path="$1"
  [[ -f "${path}" ]] || { echo "required file missing: ${path}" >&2; exit 2; }
}

require_dir() {
  local path="$1"
  [[ -d "${path}" ]] || { echo "required directory missing: ${path}" >&2; exit 2; }
}

require_file "${SOURCE_SCENE}"
require_file "${SOURCE_DENSE_PLY}"
require_dir "${SOURCE_IMAGES}"
require_dir "${SOURCE_DATA}"

ACTUAL_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${OPENMVS_IMAGE}")"
if [[ "${ACTUAL_IMAGE_ID}" != "${EXPECTED_OPENMVS_IMAGE_ID}" ]]; then
  echo "OpenMVS image mismatch: expected ${EXPECTED_OPENMVS_IMAGE_ID}, got ${ACTUAL_IMAGE_ID}" >&2
  exit 3
fi

if [[ -e "${RUN_ROOT}" ]]; then
  echo "add-once output already exists: ${RUN_ROOT}" >&2
  exit 4
fi

if [[ "${1:-}" == "--check" ]]; then
  printf 'task_id=%s\nsource_scene=%s\nsource_dense_ply=%s\nsource_images=%s\noutput=%s\nimage_id=%s\n' \
    "${JBGS_TASK_ID}" "${SOURCE_SCENE}" "${SOURCE_DENSE_PLY}" "${SOURCE_IMAGES}" \
    "${RUN_ROOT}" "${ACTUAL_IMAGE_ID}"
  exit 0
fi

STARTED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
REPOSITORY_COMMIT="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
RUNNER_UID="$(id -u)"
RUNNER_GID="$(id -g)"

mkdir -p "${WORK_OPENMVS}" "${WORK_IMAGES}"
cp --preserve=timestamps "${SOURCE_SCENE}" "${WORK_OPENMVS}/scene.mvs"
chmod a-w "${WORK_OPENMVS}/scene.mvs"

SOURCE_SCENE_SHA256="$(sha256sum "${SOURCE_SCENE}" | awk '{print $1}')"
SOURCE_DENSE_PLY_SHA256="$(sha256sum "${SOURCE_DENSE_PLY}" | awk '{print $1}')"

printf '%s\n' \
  "task_id=${JBGS_TASK_ID}" \
  "state=running" \
  "started_utc=${STARTED_UTC}" \
  "repository_commit=${REPOSITORY_COMMIT}" \
  "openmvs_image=${OPENMVS_IMAGE}" \
  "openmvs_image_id=${ACTUAL_IMAGE_ID}" \
  "source_scene=${SOURCE_SCENE}" \
  "source_scene_sha256=${SOURCE_SCENE_SHA256}" \
  "source_dense_ply=${SOURCE_DENSE_PLY}" \
  "source_dense_ply_sha256=${SOURCE_DENSE_PLY_SHA256}" \
  "source_images=${SOURCE_IMAGES}" \
  "output_root=${RUN_ROOT}" \
  "mvs_resolution_level=${MVS_RESOLUTION_LEVEL}" \
  "mvs_max_resolution=${MVS_MAX_RESOLUTION}" \
  "mvs_min_resolution=${MVS_MIN_RESOLUTION}" \
  "mvs_number_views=${MVS_NUMBER_VIEWS}" \
  "mvs_number_views_fuse=${MVS_NUMBER_VIEWS_FUSE}" \
  "mvs_estimate_colors=${MVS_ESTIMATE_COLORS}" \
  "mvs_estimate_normals=${MVS_ESTIMATE_NORMALS}" \
  "mvs_max_threads=${MVS_MAX_THREADS}" > "${RECEIPT_PATH}"

set +e
docker run --rm \
  --read-only \
  --network none \
  --user "${RUNNER_UID}:${RUNNER_GID}" \
  --env HOME=/tmp \
  --tmpfs /tmp:rw,noexec,nosuid,size=1g \
  --volume "${RUN_ROOT}:/run:rw" \
  --volume "${SOURCE_DATA}:/workspace/data:ro" \
  --workdir /run/work/mvs/openmvs \
  "${OPENMVS_IMAGE}" \
  /usr/local/bin/OpenMVS/DensifyPointCloud \
    -i scene.mvs \
    -o dim_dense.ply \
    --resolution-level "${MVS_RESOLUTION_LEVEL}" \
    --max-resolution "${MVS_MAX_RESOLUTION}" \
    --min-resolution "${MVS_MIN_RESOLUTION}" \
    --number-views "${MVS_NUMBER_VIEWS}" \
    --number-views-fuse "${MVS_NUMBER_VIEWS_FUSE}" \
    --estimate-colors "${MVS_ESTIMATE_COLORS}" \
    --estimate-normals "${MVS_ESTIMATE_NORMALS}" \
    --max-threads "${MVS_MAX_THREADS}" 2>&1 | tee "${LOG_PATH}"
DENSIFY_EXIT_CODE=${PIPESTATUS[0]}
set -e

FINISHED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '%s\n' "finished_utc=${FINISHED_UTC}" "densify_exit_code=${DENSIFY_EXIT_CODE}" >> "${RECEIPT_PATH}"

if [[ "${DENSIFY_EXIT_CODE}" -ne 0 ]]; then
  printf '%s\n' "state=failed" >> "${RECEIPT_PATH}"
  exit "${DENSIFY_EXIT_CODE}"
fi

require_file "${WORK_OPENMVS}/dim_dense.ply"
require_file "${WORK_OPENMVS}/dim_dense.mvs"

RECOVERED_DENSE_PLY_SHA256="$(sha256sum "${WORK_OPENMVS}/dim_dense.ply" | awk '{print $1}')"
RECOVERED_DENSE_MVS_SHA256="$(sha256sum "${WORK_OPENMVS}/dim_dense.mvs" | awk '{print $1}')"
if [[ "${SOURCE_DENSE_PLY_SHA256}" == "${RECOVERED_DENSE_PLY_SHA256}" ]]; then
  COMPARISON_STATE=byte_identical
  COMPARISON_EXIT_CODE=0
else
  COMPARISON_STATE=sha256_mismatch_stop_before_mesh
  COMPARISON_EXIT_CODE=10
fi

printf '%s\n' \
  "comparison_state=${COMPARISON_STATE}" \
  "source_dense_ply_sha256=${SOURCE_DENSE_PLY_SHA256}" \
  "recovered_dense_ply_sha256=${RECOVERED_DENSE_PLY_SHA256}" \
  "recovered_dense_mvs_sha256=${RECOVERED_DENSE_MVS_SHA256}" \
  "source_dense_ply_bytes=$(stat -c %s "${SOURCE_DENSE_PLY}")" \
  "recovered_dense_ply_bytes=$(stat -c %s "${WORK_OPENMVS}/dim_dense.ply")" \
  "recovered_dense_mvs_bytes=$(stat -c %s "${WORK_OPENMVS}/dim_dense.mvs")" > "${COMPARISON_PATH}"

printf '%s\n' \
  "state=complete" \
  "comparison_state=${COMPARISON_STATE}" \
  "recovered_dense_ply_sha256=${RECOVERED_DENSE_PLY_SHA256}" \
  "recovered_dense_mvs_sha256=${RECOVERED_DENSE_MVS_SHA256}" >> "${RECEIPT_PATH}"

exit "${COMPARISON_EXIT_CODE}"
