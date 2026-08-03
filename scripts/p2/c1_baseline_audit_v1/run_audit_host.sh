#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${1:?usage: run_audit_host.sh ARTIFACT_ROOT PROJECT_IMAGE_ID}"
PROJECT_IMAGE_ID="${2:?missing project image ID}"
SOURCE_ROOT="${ARTIFACT_ROOT}/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1"
TASK_ROOT="${ARTIFACT_ROOT}/phase-payloads/p2/c1_baseline_audit_v1/P2-C1-BASELINE-AUDIT-v1"
C1_CITY="${SOURCE_ROOT}/operations/C1_L_upper/C1_L_upper_COMP_84a837b5d7c79565f0e8/work/out/690792_5335864.city.jsonl"
VAL3DITY_IMAGE="jointbuildgs-p0-tools:t0"
EXPECTED_VAL3DITY_ID="sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"

[[ ! -e "${TASK_ROOT}" ]]
mkdir -p "${TASK_ROOT}/g2"
[[ "$(docker image inspect --format '{{.Id}}' "${VAL3DITY_IMAGE}")" == "${EXPECTED_VAL3DITY_ID}" ]]

set +e
docker run --rm -i --network none "${VAL3DITY_IMAGE}" \
  val3dity --overlap_tol -1.0 --planarity_d2p_tol 0.01 --planarity_n_tol 20.0 --snap_tol 0.001 stdin \
  <"${C1_CITY}" >"${TASK_ROOT}/g2/stdout.txt" 2>"${TASK_ROOT}/g2/stderr.txt"
code=$?
set -e
printf '%s\n' "${code}" >"${TASK_ROOT}/g2/exit_code.txt"

docker run --rm --network none --entrypoint /opt/conda/bin/python \
  -v "${REPO}:/workspace/JointBuildGS:ro" \
  -v "${SOURCE_ROOT}:/source:ro" -v "${TASK_ROOT}:/output:rw" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  -m src.evaluation.c1_baseline_audit_v1.evaluator \
  --source-root /source --g2-stdout /output/g2/stdout.txt \
  --g2-exit-code /output/g2/exit_code.txt --output-root /output

