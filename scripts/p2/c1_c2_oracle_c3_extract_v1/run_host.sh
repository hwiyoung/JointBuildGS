#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${1:?usage: run_host.sh ARTIFACT_ROOT PROJECT_IMAGE_ID SOURCE_COMMIT RUN_ID}"
PROJECT_IMAGE_ID="${2:?missing project image ID}"
SOURCE_COMMIT="${3:?missing source commit}"
RUN_ID="${4:?missing run ID}"
TASK_REL="phase-payloads/p2/c1_c2_oracle_c3_extract_v1/P2-C1-C2-ORACLE-C3-EXTRACT-v1"
FINAL_ROOT="${ARTIFACT_ROOT}/${TASK_REL}"
OUTPUT_ROOT="${FINAL_ROOT}.partial"
CONFIG_REL="configs/p2/c1_c2_oracle_c3_extract_v1/run_v1.json"
PACKET_REL="docs/handoffs/P2_W2C_C1_C2_ORACLE_C3_EXTRACT_v1.md"
ACCEPTED_REL="artifacts/manifests/handoffs/P2-W2C-C1-C2-ORACLE-C3-EXTRACT-v1/100-accepted.json"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
C1="${ARTIFACT_ROOT}/phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz"
C2="${ARTIFACT_ROOT}/phase-payloads/p0-audit/data/work/mvs/openmvs/dim_dense.ply"
LOD2="${ARTIFACT_ROOT}/phase-payloads/p0-audit/data/raw/lod2/690_5336.gml"
DATA_ROOT="${ARTIFACT_ROOT}/phase-payloads/p0-audit/data/work/mvs/colmap_dense"
C3_ROOT="${ARTIFACT_ROOT}/phase-payloads/p2/c1_c2_c3_utarget199_v1/P2-C1-C2-C3-UTARGET199-C3-2-GPU0-RECOVERY-v1"
C3_1="${C3_ROOT}/c3/c3_1_sem/seed0/ckpt/final.pt"
C3_2="${C3_ROOT}/c3/c3_2_sem_depth/seed0/ckpt/final.pt"

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
for path in "${C1}" "${C2}" "${LOD2}" "${C3_1}" "${C3_2}"; do
  if [[ ! -f "${path}" || -L "${path}" ]]; then
    echo "exact input missing/non-regular: ${path}" >&2
    exit 2
  fi
done

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
if [[ ! -f "${REPO}/${ACCEPTED_REL}" ]]; then
  echo "exact 100-accepted receipt is missing" >&2
  exit 2
fi
docker run --rm --network none --entrypoint /opt/conda/bin/python \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace/JointBuildGS \
  -v "${REPO}:/workspace/JointBuildGS:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/repository/validate_two_host_handoff.py "${ACCEPTED_REL}" \
    --repo . --origin-ref origin/main --head-ref HEAD
docker run --rm --network none --entrypoint /opt/conda/bin/python \
  -e EXPECTED_IMAGE="${PROJECT_IMAGE_ID}" -e EXPECTED_SOURCE="${SOURCE_COMMIT}" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" -c \
  'import json,os; r=json.load(open("artifacts/manifests/handoffs/P2-W2C-C1-C2-ORACLE-C3-EXTRACT-v1/100-accepted.json")); c=json.load(open("configs/p2/c1_c2_oracle_c3_extract_v1/run_v1.json")); assert r["handoff_id"]==c["handoff_id"] and r["task_id"]==c["task_id"]; assert r["state"]=="accepted" and r["direction"]=="work_to_experiment"; assert r["sender_role"]=="work_host" and r["receiver_role"]=="experiment_host"; assert r["receiver_ack"]["status"]=="accepted" and r["transport"]["exclusive_writer_ack"] is True; assert r["verification"]["docker_image_digest"]==os.environ["EXPECTED_IMAGE"]; assert c["status"]=="APPROVED_FOR_EXECUTION"'

mkdir -p "${OUTPUT_ROOT}"

project_run() {
  docker run --rm --network none --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
    -v "${REPO}:/workspace/JointBuildGS:ro" -v "${OUTPUT_ROOT}:/output:rw" \
    -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" "$@"
}

project_run scripts/p2/c1_c2_oracle_c3_extract_v1/prepare_c1_c2.py preflight
docker run --rm --network none --cpus 4 --memory 32g --pids-limit 1024 \
  --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -v "${OUTPUT_ROOT}:/output:rw" \
  -v "${C1}:/inputs/c1.laz:ro" -v "${C2}:/inputs/c2.ply:ro" -v "${LOD2}:/inputs/lod2.gml:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2/c1_c2_oracle_c3_extract_v1/prepare_c1_c2.py prepare \
    --output-root /output --c1 /inputs/c1.laz --c2 /inputs/c2.ply --lod2 /inputs/lod2.gml

while IFS=$'\t' read -r operation_unit_id work_relative; do
  [[ "${operation_unit_id}" == "operation_unit_id" ]] && continue
  work="${OUTPUT_ROOT}/${work_relative}"
  mkdir "${work}/out"
  start="${SECONDS}"
  set +e
  timeout 600 docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
    --user "$(id -u):$(id -g)" -v "${work}:/work:rw" -w /work "${ROOFER_IMAGE}" \
    --id-attribute stable_id --jobs 1 --srs EPSG:25832 --bld-class 6 --grnd-class 2 --lod22 \
    input.las gt_footprint_oracle.geojson out >"${work}/runtime.log" 2>&1
  code=$?
  set -e
  project_run scripts/p2/c1_c2_oracle_c3_extract_v1/prepare_c1_c2.py record-terminal \
    --output-root /output --operation-unit-id "${operation_unit_id}" \
    --exit-code "${code}" --runtime-seconds "$((SECONDS - start))"
done <"${OUTPUT_ROOT}/freeze/c1_c2_execution_units_v1.tsv"

for item in "C3_1_SEM:${C3_1}" "C3_2_SEM_DEPTH:${C3_2}"; do
  condition="${item%%:*}"
  checkpoint="${item#*:}"
  docker run --rm --network none --cpus 2 --memory 12g --pids-limit 512 \
    --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
    -v "${REPO}:/workspace/JointBuildGS:ro" -v "${OUTPUT_ROOT}:/output:rw" \
    -v "${checkpoint}:/inputs/final.pt:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
    scripts/p2/c1_c2_oracle_c3_extract_v1/extract_c3.py prepare-condition \
      --output-root /output --checkpoint /inputs/final.pt --condition-id "${condition}" --hash-checkpoint
  docker run --rm --network none --gpus device=0 --cpus 4 --memory 48g --pids-limit 1024 \
    --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
    -v "${REPO}:/workspace/JointBuildGS:ro" -v "${ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro" \
    -v "${OUTPUT_ROOT}:/output:rw" -v "${checkpoint}:/inputs/final.pt:ro" -v "${LOD2}:/inputs/lod2.gml:ro" \
    -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
    scripts/p2/c1_c2_oracle_c3_extract_v1/extract_c3.py extract-surfaces \
      --output-root /output --artifact-root /artifacts/JointBuildGS \
      --checkpoint /inputs/final.pt --lod2 /inputs/lod2.gml --condition-id "${condition}" --device cuda
done

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
