#!/usr/bin/env bash
set -euo pipefail

# Thin Experiment-Host wrapper. A reviewed handoff must bind SOURCE_COMMIT and
# mount only the exact R4 checkpoint first; the R3 score cells are mounted only
# in the second container after the add-once geometry freeze exists.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${1:?usage: run_stage3_host.sh ARTIFACT_ROOT PROJECT_IMAGE_ID SOURCE_COMMIT RUN_ID}"
PROJECT_IMAGE_ID="${2:?missing project image ID}"
SOURCE_COMMIT="${3:?missing source commit}"
RUN_ID="${4:?missing run ID}"
TASK_REL="phase-payloads/p2/c3_development_stage3_v1/P2-C3-DEVELOPMENT-STAGE3-v1"
TASK_ROOT="${ARTIFACT_ROOT}/${TASK_REL}"
R4_REL="phase-payloads/p2/c1_c2_g2_c3_first_wave_recovery_r4_v1/P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R4-v1"
R3_REL="phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1"
FINAL_PT="${ARTIFACT_ROOT}/${R4_REL}/c3/train/seed0/ckpt/final.pt"
SCORE_CELLS="${ARTIFACT_ROOT}/${R3_REL}/freeze/development_score_cells_v1.jsonl"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
ACCEPTED_RECEIPT_REL="artifacts/manifests/handoffs/P2-W2C-C3-DEVELOPMENT-STAGE3-v1/100-accepted.json"
PACKET_REL="docs/handoffs/P2_W2C_C3_DEVELOPMENT_STAGE3_v1.md"
PACKET_AUTHORITY_PARSER="${REPO}/scripts/p2_baselines/c1_c2_feasibility_pilot_v1/parse_execution_authority.awk"

timeout 300 git -C "${REPO}" fetch origin main
HEAD_SHA="$(git -C "${REPO}" rev-parse HEAD)"
ORIGIN_SHA="$(git -C "${REPO}" rev-parse origin/main)"
PACKET_SOURCE_COMMIT="$(sed -n 's/^- source_commit: `\([0-9a-f]\{40\}\)`.*$/\1/p' "${REPO}/${PACKET_REL}")"
if [[ "${HEAD_SHA}" != "${ORIGIN_SHA}" || "${PACKET_SOURCE_COMMIT}" != "${SOURCE_COMMIT}" \
  || -n "$(git -C "${REPO}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "HEAD/origin/source or clean-state authority mismatch" >&2
  exit 2
fi
if [[ ! -f "${REPO}/${ACCEPTED_RECEIPT_REL}" ]] \
  || ! awk -f "${PACKET_AUTHORITY_PARSER}" "${REPO}/${PACKET_REL}"; then
  echo "exact accepted receipt or activated packet is missing" >&2
  exit 2
fi
docker run --rm --network none --entrypoint /opt/conda/bin/python \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace/JointBuildGS \
  -v "${REPO}:/workspace/JointBuildGS:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/repository/validate_two_host_handoff.py "${ACCEPTED_RECEIPT_REL}" \
    --repo . --origin-ref origin/main --head-ref HEAD
docker run --rm --network none --entrypoint /opt/conda/bin/python \
  -e EXPECTED_PROJECT_IMAGE_ID="${PROJECT_IMAGE_ID}" -e EXPECTED_SOURCE_COMMIT="${SOURCE_COMMIT}" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  -c 'import json,os,re; r=json.load(open("artifacts/manifests/handoffs/P2-W2C-C3-DEVELOPMENT-STAGE3-v1/100-accepted.json")); text=open("docs/handoffs/P2_W2C_C3_DEVELOPMENT_STAGE3_v1.md",encoding="utf-8").read(); assert r["handoff_id"]=="P2-W2C-C3-DEVELOPMENT-STAGE3-v1" and r["task_id"]=="P2-C3-DEVELOPMENT-STAGE3-v1"; assert r["state"]=="accepted" and r["receiver_ack"]["status"]=="accepted"; assert r["verification"]["docker_image_digest"]==os.environ["EXPECTED_PROJECT_IMAGE_ID"]; assert re.search(r"source_commit: `"+os.environ["EXPECTED_SOURCE_COMMIT"]+r"`",text)'
for path in "${FINAL_PT}" "${SCORE_CELLS}"; do
  if [[ ! -f "${path}" || -L "${path}" ]]; then
    echo "exact input missing/non-regular: ${path}" >&2
    exit 2
  fi
done
mkdir -p "${TASK_ROOT}"

project_run() {
  docker run --rm --network none --entrypoint /opt/conda/bin/python \
    --user "$(id -u):$(id -g)" \
    -v "${REPO}:/workspace/JointBuildGS:ro" \
    -v "${TASK_ROOT}:/stage3_output:rw" \
    -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
    scripts/p2/c3_development_stage3_v1/run_stage3.py "$@"
}

docker run --rm --network none --entrypoint /opt/conda/bin/python \
  --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" \
  -v "${TASK_ROOT}:/stage3_output:rw" \
  -v "${FINAL_PT}:/stage3_inputs/final.pt:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2/c3_development_stage3_v1/run_stage3.py prepare-geometry \
    --output-root /stage3_output --checkpoint /stage3_inputs/final.pt \
    --source-commit "${SOURCE_COMMIT}" --run-id "${RUN_ID}"

docker run --rm --network none --entrypoint /opt/conda/bin/python \
  --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" \
  -v "${TASK_ROOT}:/stage3_output:rw" \
  -v "${SCORE_CELLS}:/stage3_inputs/development_score_cells_v1.jsonl:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2/c3_development_stage3_v1/run_stage3.py associate-development \
    --output-root /stage3_output --score-cells /stage3_inputs/development_score_cells_v1.jsonl \
    --source-commit "${SOURCE_COMMIT}" --run-id "${RUN_ID}"

while IFS=$'\t' read -r operation_unit_id work_relative; do
  [[ "${operation_unit_id}" == "operation_unit_id" ]] && continue
  work="${TASK_ROOT}/${work_relative}"
  if [[ -f "${work}/roofer_terminal_v1.json" ]]; then
    project_run verify-roofer-terminal --output-root /stage3_output --unit-id "${operation_unit_id}" >/dev/null
    continue
  fi
  if [[ -e "${work}/runtime.log" || -d "${work}/out" ]]; then
    echo "existing Roofer state requires review; refusing duplicate: ${operation_unit_id}" >&2
    exit 2
  fi
  mkdir "${work}/out"
  attempt_start="${SECONDS}"
  set +e
  timeout 600 docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
    --user "$(id -u):$(id -g)" -v "${work}:/work:rw" -w /work "${ROOFER_IMAGE}" \
    --id-attribute component_id --jobs 1 --srs EPSG:25832 --bld-class 6 --grnd-class 2 --lod22 \
    input.las r_derived.geojson out >"${work}/runtime.log" 2>&1
  exit_code=$?
  set -e
  runtime_seconds=$((SECONDS - attempt_start))
  project_run record-roofer-terminal --output-root /stage3_output \
    --unit-id "${operation_unit_id}" --exit-code "${exit_code}" \
    --runtime-seconds "${runtime_seconds}" >/dev/null
done <"${TASK_ROOT}/freeze/c3_execution_units_v1.tsv"

docker run --rm --network none --entrypoint /opt/conda/bin/python \
  --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" \
  -v "${TASK_ROOT}:/stage3_output:rw" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2/c3_development_stage3_v1/run_stage3.py finalize-technical \
    --output-root /stage3_output --source-commit "${SOURCE_COMMIT}" --run-id "${RUN_ID}"

echo "C3 development technical Roofer units complete; G3/G4/PASS remain null."
