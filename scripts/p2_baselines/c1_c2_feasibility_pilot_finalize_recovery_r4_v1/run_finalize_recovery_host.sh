#!/usr/bin/env bash
set -euo pipefail

# Finalize-only recovery: the sealed R3 namespace is mounted read-only and the
# fresh R4 namespace is the sole writable payload mount.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${1:?usage: run_finalize_recovery_host.sh ABS_ARTIFACT_ROOT PROJECT_IMAGE_ID SOURCE_COMMIT RUN_ID}"
PROJECT_IMAGE_ID="${2:?missing accepted project image ID}"
SOURCE_COMMIT="${3:?missing accepted source commit}"
RUN_ID="${4:?missing immutable recovery run ID}"
R3_REL="phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1"
R4_REL="phase-payloads/p2-baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/P2-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-v1"
R3_ROOT="${ARTIFACT_ROOT}/${R3_REL}"
R4_ROOT="${ARTIFACT_ROOT}/${R4_REL}"
R3_CLOSED_RECEIPT="artifacts/manifests/handoffs/P2-W2C-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1/300-closed.json"
R4_ACCEPTED_RECEIPT="artifacts/manifests/handoffs/P2-W2C-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-v1/100-accepted.json"
R4_PACKET="docs/handoffs/P2_W2C_C1_C2_FEASIBILITY_PILOT_FINALIZE_RECOVERY_R4_v1.md"
AUTHORITY_PARSER="${REPO}/scripts/p2_baselines/c1_c2_feasibility_pilot_v1/parse_execution_authority.awk"

if [[ "${ARTIFACT_ROOT}" != /* || ! -d "${ARTIFACT_ROOT}" ]]; then
  echo "artifact root must be an existing absolute directory" >&2
  exit 2
fi
if [[ ! "${PROJECT_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ || ! "${SOURCE_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "project image/source commit identity is invalid" >&2
  exit 2
fi

timeout 300 git -C "${REPO}" fetch origin main
HEAD_SHA="$(git -C "${REPO}" rev-parse HEAD)"
ORIGIN_SHA="$(git -C "${REPO}" rev-parse origin/main)"
PACKET_SOURCE_COMMIT="$(sed -n 's/^- source_commit: `\([0-9a-f]\{40\}\)`.*$/\1/p' "${REPO}/${R4_PACKET}")"
PACKET_PROJECT_IMAGE_ID="$(sed -n 's/^- project_image_id: `\(sha256:[0-9a-f]\{64\}\)`.*$/\1/p' "${REPO}/${R4_PACKET}")"
PACKET_RUN_ID="$(sed -n 's/^- run_id: `\([^`]*\)`.*$/\1/p' "${REPO}/${R4_PACKET}")"
PACKET_EXECUTION_MODE="$(sed -n 's/^- execution_mode: `\([^`]*\)`.*$/\1/p' "${REPO}/${R4_PACKET}")"
if [[ "${HEAD_SHA}" != "${ORIGIN_SHA}" || "${PACKET_SOURCE_COMMIT}" != "${SOURCE_COMMIT}" \
  || "${PACKET_PROJECT_IMAGE_ID}" != "${PROJECT_IMAGE_ID}" || "${PACKET_RUN_ID}" != "${RUN_ID}" \
  || "${PACKET_EXECUTION_MODE}" != "FINALIZE_ONLY_REUSE" \
  || -n "$(git -C "${REPO}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "HEAD/origin/source or clean-state authority mismatch" >&2
  exit 2
fi
if [[ ! -f "${REPO}/${R4_ACCEPTED_RECEIPT}" || ! -f "${REPO}/${R3_CLOSED_RECEIPT}" ]]; then
  echo "required accepted/closed receipt is missing" >&2
  exit 2
fi
if ! awk -f "${AUTHORITY_PARSER}" "${REPO}/${R4_PACKET}"; then
  echo "R4 packet is not explicitly activated" >&2
  exit 2
fi
ACCEPTED_RECEIPT_COMMIT="$(git -C "${REPO}" log -1 --format=%H -- "${R4_ACCEPTED_RECEIPT}")"
if [[ "${ACCEPTED_RECEIPT_COMMIT}" != "${HEAD_SHA}" ]]; then
  echo "100-accepted receipt is not the exact current commit" >&2
  exit 2
fi

# Artifact verification belongs to the 100 lifecycle. This preflight validates only
# exact Git/receipt authority and never receives an external artifact mount.
docker run --rm --network none --entrypoint /opt/conda/bin/python \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace/JointBuildGS \
  -v "${REPO}:/workspace/JointBuildGS:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/run_recovery.py authority-preflight \
    --source-closed-receipt "/workspace/JointBuildGS/${R3_CLOSED_RECEIPT}" \
    --accepted-receipt "/workspace/JointBuildGS/${R4_ACCEPTED_RECEIPT}" \
    --source-commit "${SOURCE_COMMIT}" --accepted-commit "${ACCEPTED_RECEIPT_COMMIT}" \
    --project-image-id "${PROJECT_IMAGE_ID}" --run-id "${RUN_ID}"

if [[ ! -d "${R3_ROOT}" || -L "${R3_ROOT}" ]]; then
  echo "sealed R3 source namespace is missing or symlinked" >&2
  exit 2
fi
if [[ -e "${R4_ROOT}" ]]; then
  echo "fresh R4 namespace already exists" >&2
  exit 2
fi
mkdir -p "${R4_ROOT}"

docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
  --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace/JointBuildGS \
  -v "${REPO}:/workspace/JointBuildGS:ro" \
  -v "${R3_ROOT}:/r3_source:ro" \
  -v "${R4_ROOT}:/r4_output:rw" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/run_recovery.py recover-finalize \
    --source-root /r3_source --output-root /r4_output \
    --source-closed-receipt "/workspace/JointBuildGS/${R3_CLOSED_RECEIPT}" \
    --accepted-receipt "/workspace/JointBuildGS/${R4_ACCEPTED_RECEIPT}" \
    --source-commit "${SOURCE_COMMIT}" --accepted-commit "${ACCEPTED_RECEIPT_COMMIT}" \
    --project-image-id "${PROJECT_IMAGE_ID}" --run-id "${RUN_ID}" \
    --handoff-id P2-W2C-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-v1 \
    --artifact-root-token artifact://JointBuildGS

# Promotion is a separate container with no R3 source mount. It reads only the new
# R4 compact results and writes the task-owned Git result paths once.
if [[ "$(git -C "${REPO}" rev-parse HEAD)" != "$(git -C "${REPO}" rev-parse origin/main)" \
  || "$(git -C "${REPO}" log -1 --format=%H -- "${R4_ACCEPTED_RECEIPT}")" != "${ACCEPTED_RECEIPT_COMMIT}" \
  || -n "$(git -C "${REPO}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "promotion authority changed after finalization" >&2
  exit 2
fi
if ! awk -f "${AUTHORITY_PARSER}" "${REPO}/${R4_PACKET}"; then
  echo "R4 packet lost execution authority before promotion" >&2
  exit 2
fi
docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
  --entrypoint /opt/conda/bin/python --user "$(id -u):$(id -g)" \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/workspace/JointBuildGS \
  -v "${REPO}:/workspace/JointBuildGS:rw" \
  -v "${R4_ROOT}:/r4_output:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  scripts/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/run_recovery.py promote \
    --output-root /r4_output --repo-root /workspace/JointBuildGS \
    --promotion-parent-commit "${ACCEPTED_RECEIPT_COMMIT}"

echo "R4 finalize-only recovery and compact promotion completed without reconstruction execution."
