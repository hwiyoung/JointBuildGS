#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${1:?usage: run_contract_host.sh ARTIFACT_ROOT PROJECT_IMAGE_ID SOURCE_COMMIT RUN_ID}"
PROJECT_IMAGE_ID="${2:?missing project image ID}"
SOURCE_COMMIT="${3:?missing source commit}"
RUN_ID="${4:?missing run ID}"
TASK_REL="phase-payloads/p2/utarget199_contract_results_v1/P2-UTARGET199-CONTRACT-RESULTS-v1"
TASK_ROOT="${ARTIFACT_ROOT}/${TASK_REL}"
C1C2_REL="phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1"
C3_REL="phase-payloads/p2/c3_development_stage3_v1/P2-C3-DEVELOPMENT-STAGE3-v1"
REF_REL="phase-payloads/p0-audit/data/work/gate_s0/uas_reference_coverage_r1_v1/P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1/reference/reference_candidate_cells_v1.csv"
CHECKPOINT_REL="phase-payloads/p2/c1_c2_g2_c3_first_wave_recovery_r4_v1/P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R4-v1/c3/train/seed0/ckpt/final.pt"
BESTVIEW_REL="results/tum_transfer/mob/overseg_lever/population_aux_v4_bestview.json"
IMAGE_DIR_REL="phase-payloads/p0-audit/data/work/images/Images"
CAMERAS_REL="phase-payloads/p0-audit/data/work/colmap/sparse/0/cameras.txt"
IMAGES_REL="phase-payloads/p0-audit/data/work/colmap/sparse/0/images.txt"
SCENE_REL="phase-payloads/p0-audit/data/work/opf/opf/scene_reference_frame.json"
PACKET_REL="docs/handoffs/P2_W2C_UTARGET199_CONTRACT_RESULTS_v1.md"
ACCEPTED_REL="artifacts/manifests/handoffs/P2-W2C-UTARGET199-CONTRACT-RESULTS-v1/100-accepted.json"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
G2_IMAGE="jointbuildgs-p0-tools:t0"
EXPECTED_G2_ID="sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"
START_SECONDS="${SECONDS}"
HARD_CAP_SECONDS=43200

timeout 300 git -C "${REPO}" fetch origin main
HEAD_SHA="$(git -C "${REPO}" rev-parse HEAD)"
ORIGIN_SHA="$(git -C "${REPO}" rev-parse origin/main)"
PACKET_SOURCE_COMMIT="$(sed -n 's/^- source_commit: `\([0-9a-f]\{40\}\)`.*$/\1/p' "${REPO}/${PACKET_REL}")"
if [[ "${HEAD_SHA}" != "${ORIGIN_SHA}" || "${PACKET_SOURCE_COMMIT}" != "${SOURCE_COMMIT}" \
  || -n "$(git -C "${REPO}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "HEAD/origin/source/clean authority mismatch" >&2
  exit 2
fi
if [[ ! -f "${REPO}/${ACCEPTED_REL}" ]]; then
  echo "accepted receipt missing" >&2
  exit 2
fi
docker run --rm --network none --entrypoint /opt/conda/bin/python \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace/JointBuildGS \
  -v "${REPO}:/workspace/JointBuildGS:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/repository/validate_two_host_handoff.py "${ACCEPTED_REL}" --repo . --origin-ref origin/main --head-ref HEAD
if [[ "$(docker image inspect "${G2_IMAGE}" --format '{{.Id}}')" != "${EXPECTED_G2_ID}" ]]; then
  echo "pinned val3dity image differs" >&2
  exit 2
fi
for path in \
  "${ARTIFACT_ROOT}/${C1C2_REL}/freeze/all_condition_jobs_v1.jsonl" \
  "${ARTIFACT_ROOT}/${C1C2_REL}/freeze/condition_components_v1.jsonl" \
  "${ARTIFACT_ROOT}/${C3_REL}/freeze/c3_all_jobs_v1.jsonl" \
  "${ARTIFACT_ROOT}/${C3_REL}/freeze/c3_condition_components_v1.jsonl" \
  "${ARTIFACT_ROOT}/${REF_REL}" "${ARTIFACT_ROOT}/${CHECKPOINT_REL}" \
  "${ARTIFACT_ROOT}/${BESTVIEW_REL}" "${ARTIFACT_ROOT}/${CAMERAS_REL}" \
  "${ARTIFACT_ROOT}/${IMAGES_REL}" "${ARTIFACT_ROOT}/${SCENE_REL}"; do
  [[ -f "${path}" && ! -L "${path}" ]] || { echo "exact input missing/non-regular: ${path}" >&2; exit 2; }
done
[[ -d "${ARTIFACT_ROOT}/${IMAGE_DIR_REL}" && ! -L "${ARTIFACT_ROOT}/${IMAGE_DIR_REL}" ]] || { echo "image directory missing" >&2; exit 2; }
mkdir -p "${TASK_ROOT}"

project_run() {
  docker run --rm --network none --entrypoint /opt/conda/bin/python \
    --user "$(id -u):$(id -g)" --cpus 4 --memory 16g --pids-limit 1024 \
    -v "${REPO}:/workspace/JointBuildGS:ro" \
    -v "${TASK_ROOT}:/task:rw" \
    -v "${ARTIFACT_ROOT}/${C1C2_REL}:/sources/c1c2:ro" \
    -v "${ARTIFACT_ROOT}/${C3_REL}:/sources/c3:ro" \
    -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
    scripts/p2/utarget199_contract_results_v1/run_contract.py "$@"
}

project_run preflight
project_run prepare --output-root /task --c1-c2-source-root /sources/c1c2 --c3-source-root /sources/c3 \
  --source-commit "${SOURCE_COMMIT}" --run-id "${RUN_ID}"

while IFS=$'\t' read -r unit_id work_relative reused; do
  [[ "${unit_id}" == "operation_unit_id" ]] && continue
  if [[ "${reused}" == "true" ]]; then
    project_run verify-terminal --output-root /task --unit-id "${unit_id}" >/dev/null
    continue
  fi
  work="${TASK_ROOT}/${work_relative}"
  terminal_slug="$(printf '%s' "${unit_id}" | sha256sum | cut -c1-24)"
  if [[ -f "${TASK_ROOT}/terminal/${terminal_slug}.json" ]]; then
    project_run verify-terminal --output-root /task --unit-id "${unit_id}" >/dev/null
    continue
  fi
  if [[ -e "${work}/runtime.log" || -d "${work}/out" ]]; then
    echo "partial Roofer state refuses duplicate execution: ${unit_id}" >&2
    exit 2
  fi
  mkdir "${work}/out"
  begin="${SECONDS}"
  set +e
  timeout 600 docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
    --user "$(id -u):$(id -g)" -v "${work}:/work:rw" -w /work "${ROOFER_IMAGE}" \
    --id-attribute component_id --jobs 1 --srs EPSG:25832 --bld-class 6 --grnd-class 2 --lod22 \
    input.las r_derived.geojson out >"${work}/runtime.log" 2>&1
  exit_code=$?
  set -e
  project_run record-roofer-terminal --output-root /task --unit-id "${unit_id}" \
    --exit-code "${exit_code}" --runtime-seconds "$((SECONDS - begin))" >/dev/null
  if (( SECONDS - START_SECONDS > HARD_CAP_SECONDS )); then
    echo "12-hour cap exceeded" >&2
    exit 2
  fi
done <"${TASK_ROOT}/freeze/execution_units_v1.tsv"

G2_OUTPUT="${TASK_ROOT}/results/g2_unique_operation_receipts_v1.jsonl"
if [[ ! -f "${G2_OUTPUT}" ]]; then
  docker run --rm --network none --entrypoint python3 --user "$(id -u):$(id -g)" \
    -v "${REPO}:/workspace/JointBuildGS:ro" -v "${TASK_ROOT}:/task:rw" \
    -w /workspace/JointBuildGS "${G2_IMAGE}" \
    scripts/p2/utarget199_contract_results_v1/run_g2_batch.py \
      --task-root /task --units /task/freeze/execution_units_v1.jsonl \
      --output /task/results/g2_unique_operation_receipts_v1.jsonl
fi

docker run --rm --network none --entrypoint /opt/conda/bin/python \
  --user "$(id -u):$(id -g)" --cpus 4 --memory 16g --pids-limit 1024 \
  -v "${REPO}:/workspace/JointBuildGS:ro" -v "${TASK_ROOT}:/task:rw" \
  -v "${ARTIFACT_ROOT}/${REF_REL}:/inputs/reference_candidate_cells_v1.csv:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2/utarget199_contract_results_v1/run_contract.py finalize \
    --output-root /task --reference-cells /inputs/reference_candidate_cells_v1.csv \
    --g2-receipts /task/results/g2_unique_operation_receipts_v1.jsonl \
    --source-commit "${SOURCE_COMMIT}" --run-id "${RUN_ID}"

if [[ ! -f "${TASK_ROOT}/control/qualitative_complete_v1.json" ]]; then
  docker run --rm --network none --entrypoint /opt/conda/bin/python \
    --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
    -v "${REPO}:/workspace/JointBuildGS:ro" -v "${TASK_ROOT}:/task:rw" \
    -v "${ARTIFACT_ROOT}/${BESTVIEW_REL}:/render_inputs/${BESTVIEW_REL}:ro" \
    -v "${ARTIFACT_ROOT}/${IMAGE_DIR_REL}:/render_inputs/${IMAGE_DIR_REL}:ro" \
    -v "${ARTIFACT_ROOT}/${CAMERAS_REL}:/render_inputs/${CAMERAS_REL}:ro" \
    -v "${ARTIFACT_ROOT}/${IMAGES_REL}:/render_inputs/${IMAGES_REL}:ro" \
    -v "${ARTIFACT_ROOT}/${SCENE_REL}:/render_inputs/${SCENE_REL}:ro" \
    -v "${ARTIFACT_ROOT}/${CHECKPOINT_REL}:/inputs/final.pt:ro" \
    -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
    scripts/p2/utarget199_contract_results_v1/render_case_sheets.py \
      --task-root /task --artifact-root /render_inputs --checkpoint /inputs/final.pt
fi

output_bytes="$(du -sb -- "${TASK_ROOT}" | cut -f1)"
if (( output_bytes > 5000000000 )); then
  echo "5GB output cap exceeded" >&2
  exit 2
fi
echo "U_target 199 x C1/C2/C3 metrics and 199 Sheet A/B/C figures complete."
