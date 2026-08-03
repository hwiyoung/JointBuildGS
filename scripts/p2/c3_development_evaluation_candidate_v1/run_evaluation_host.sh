#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${1:?usage: run_evaluation_host.sh ARTIFACT_ROOT PROJECT_IMAGE_ID SOURCE_COMMIT}"
PROJECT_IMAGE_ID="${2:?missing project image ID}"
SOURCE_COMMIT="${3:?missing source commit}"
C3_ROOT="${ARTIFACT_ROOT}/phase-payloads/p2/c3_development_stage3_v1/P2-C3-DEVELOPMENT-STAGE3-v1"
R4_ROOT="${ARTIFACT_ROOT}/phase-payloads/p2/c1_c2_g2_c3_first_wave_recovery_r4_v1/P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R4-v1"
R3_ROOT="${ARTIFACT_ROOT}/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1"
TASK_ROOT="${ARTIFACT_ROOT}/phase-payloads/p2/c3_development_evaluation_candidate_v1/P2-C3-DEVELOPMENT-EVALUATION-CANDIDATE-v1"
VAL3DITY_IMAGE="jointbuildgs-p0-tools:t0"
EXPECTED_VAL3DITY_ID="sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"
RECEIPT="artifacts/manifests/handoffs/P2-W2C-C3-DEVELOPMENT-EVALUATION-CANDIDATE-v1/100-accepted.json"
PACKET="docs/handoffs/P2_W2C_C3_DEVELOPMENT_EVALUATION_CANDIDATE_v1.md"

timeout 300 git -C "${REPO}" fetch origin main
[[ "$(git -C "${REPO}" rev-parse HEAD)" == "$(git -C "${REPO}" rev-parse origin/main)" ]]
[[ -z "$(git -C "${REPO}" status --porcelain=v1 --untracked-files=all)" ]]
grep -Fq "source_commit: \`${SOURCE_COMMIT}\`" "${REPO}/${PACKET}"

docker run --rm --network none --entrypoint /opt/conda/bin/python \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace/JointBuildGS \
  -v "${REPO}:/workspace/JointBuildGS:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/repository/validate_two_host_handoff.py "${RECEIPT}" --repo . --origin-ref origin/main --head-ref HEAD
[[ "$(docker image inspect --format '{{.Id}}' "${VAL3DITY_IMAGE}")" == "${EXPECTED_VAL3DITY_ID}" ]]
[[ ! -e "${TASK_ROOT}" ]]
mkdir -p "${TASK_ROOT}"

docker run --rm --network none --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -v "${C3_ROOT}:/c3:ro" -v "${TASK_ROOT}:/output:rw" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2/c3_development_evaluation_candidate_v1/run_evaluation.py prepare --c3-root /c3 --output-root /output

while IFS=$'\t' read -r unit_id unit_key city_rel; do
  [[ "${unit_id}" == "operation_unit_id" ]] && continue
  work="${TASK_ROOT}/g2/${unit_key}"
  mkdir -p "${work}"
  set +e
  docker run --rm --network none --entrypoint /bin/sh \
    -v "${C3_ROOT}/${city_rel}:/input.city.jsonl:ro" "${VAL3DITY_IMAGE}" \
    -c 'val3dity --overlap_tol -1.0 --planarity_d2p_tol 0.01 --planarity_n_tol 20.0 --snap_tol 0.001 stdin < /input.city.jsonl' \
    >"${work}/stdout.txt" 2>"${work}/stderr.txt"
  code=$?
  set -e
  [[ "${code}" -eq 0 || "${code}" -eq 1 ]]
  printf '%s\n' "${code}" >"${work}/exit_code.txt"
done <"${TASK_ROOT}/freeze/evaluation_units_v1.tsv"

docker run --rm --network none --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -v "${C3_ROOT}:/c3:ro" -v "${TASK_ROOT}:/output:rw" \
  -v "${R3_ROOT}/freeze/development_score_cells_v1.jsonl:/inputs/score_cells.jsonl:ro" \
  -v "${R3_ROOT}:/c1c2_source:ro" \
  -v "${R4_ROOT}/c1_c2/development_diagnostics_v1.jsonl:/inputs/c1_c2.jsonl:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2/c3_development_evaluation_candidate_v1/run_evaluation.py evaluate \
  --c3-root /c3 --score-cells /inputs/score_cells.jsonl \
  --c1-c2-diagnostics /inputs/c1_c2.jsonl --c1-c2-source-root /c1c2_source \
  --output-root /output
