#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${1:?usage: run_host.sh ARTIFACT_ROOT PROJECT_IMAGE_ID SOURCE_COMMIT RUN_ID}"
PROJECT_IMAGE_ID="${2:?missing project image ID}"
SOURCE_COMMIT="${3:?missing source commit}"
RUN_ID="${4:?missing run ID}"
TASK_REL="phase-payloads/p2/c1_c2_oracle_c3_extract_recovery_v4/P2-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v4"
FINAL_ROOT="${ARTIFACT_ROOT}/${TASK_REL}"
OUTPUT_ROOT="${FINAL_ROOT}.partial"
CONFIG_REL="configs/p2/c1_c2_oracle_c3_extract_v1/run_v1.json"
RECOVERY_SOURCE="${ARTIFACT_ROOT}/phase-payloads/p2/c1_c2_oracle_c3_extract_recovery_v3/P2-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v3.partial"
LOD2="${ARTIFACT_ROOT}/phase-payloads/p0-audit/data/raw/lod2/690_5336.gml"

if [[ "${ARTIFACT_ROOT}" != /* || ! -d "${ARTIFACT_ROOT}" ]]; then
  echo "artifact root must be an existing absolute directory" >&2
  exit 2
fi
if [[ ! "${PROJECT_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ || ! "${SOURCE_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "project image/source commit identity is invalid" >&2
  exit 2
fi
if [[ -e "${FINAL_ROOT}" || -e "${OUTPUT_ROOT}" ]]; then
  echo "final/partial add-once namespace already exists" >&2
  exit 2
fi
for path in "${LOD2}"; do
  if [[ ! -f "${path}" || -L "${path}" ]]; then
    echo "exact input missing/non-regular: ${path}" >&2
    exit 2
  fi
done
if [[ ! -d "${RECOVERY_SOURCE}" || -L "${RECOVERY_SOURCE}" ]]; then
  echo "preserved C1/C2/C3 recovery source missing/non-directory" >&2
  exit 2
fi

timeout 300 git -C "${REPO}" fetch origin main
HEAD_SHA="$(git -C "${REPO}" rev-parse HEAD)"
ORIGIN_SHA="$(git -C "${REPO}" rev-parse origin/main)"
if [[ "${HEAD_SHA}" != "${ORIGIN_SHA}" || -n "$(git -C "${REPO}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "execution requires clean HEAD equal to origin/main" >&2
  exit 2
fi
if ! git -C "${REPO}" merge-base --is-ancestor "${SOURCE_COMMIT}" "${HEAD_SHA}"; then
  echo "source commit is not an ancestor of execution HEAD" >&2
  exit 2
fi
docker run --rm --network none --entrypoint /opt/conda/bin/python \
  -v "${REPO}:/workspace/JointBuildGS:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" -c \
  'import json; c=json.load(open("configs/p2/c1_c2_oracle_c3_extract_v1/run_v1.json")); a=c["execution_authority"]; assert c["status"]=="APPROVED_FOR_EXECUTION"; assert a["mode"]=="DIRECT_HUMAN_INSTRUCTION_SINGLE_EXPERIMENT_HOST"; assert a["execution_host_role"]=="experiment_host"; assert a["write_ownership_transfer_performed"] is False; assert a["two_host_receipt_required"] is False'

mkdir -p "${OUTPUT_ROOT}"

project_run() {
  docker run --rm --network none --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
    -v "${REPO}:/workspace/JointBuildGS:ro" -v "${OUTPUT_ROOT}:/output:rw" \
    -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" "$@"
}

docker run --rm --network none --cpus 4 --memory 32g --pids-limit 1024 \
  --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -v "${OUTPUT_ROOT}:/output:rw" -v "${RECOVERY_SOURCE}:/source-all:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2/c1_c2_oracle_c3_extract_v1/prepare_c1_c2.py inherit-completed \
    --output-root /output --source-root /source-all
docker run --rm --network none --cpus 4 --memory 32g --pids-limit 1024 \
  --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -v "${OUTPUT_ROOT}:/output:rw" -v "${RECOVERY_SOURCE}:/source-all:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2/c1_c2_oracle_c3_extract_v1/extract_c3.py inherit-completed \
    --output-root /output --source-root /source-all

docker run --rm --network none --cpus 4 --memory 32g --pids-limit 1024 \
  --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -v "${ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro" \
  -v "${OUTPUT_ROOT}:/output:rw" -v "${LOD2}:/inputs/lod2.gml:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2/c1_c2_oracle_c3_extract_v1/render_results.py c1-c2 \
    --output-root /output --artifact-root /artifacts/JointBuildGS --lod2 /inputs/lod2.gml
docker run --rm --network none --cpus 4 --memory 32g --pids-limit 1024 \
  --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -v "${OUTPUT_ROOT}:/output:rw" \
  -v "${LOD2}:/inputs/lod2.gml:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2/c1_c2_oracle_c3_extract_v1/render_results.py c3 \
    --output-root /output --lod2 /inputs/lod2.gml

project_run scripts/p2/c1_c2_oracle_c3_extract_v1/finalize.py \
  --output-root /output --source-commit "${SOURCE_COMMIT}" --run-id "${RUN_ID}"

mv -- "${OUTPUT_ROOT}" "${FINAL_ROOT}"
echo "C1/C2 six-building-method oracle operations and C3 extraction-only results finalized: ${FINAL_ROOT}"
