#!/usr/bin/env bash
set -euo pipefail

# Host-side synthetic runtime check. It performs no scientific evaluation.
# Authority preflight sees the artifact root read-only; Roofer sees only two
# synthetic inputs and its pending output; the recorder sees the artifact root
# read-only for accepted stat checks and writes only the nested task namespace.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
ARTIFACT_ROOT_HOST="${1:?usage: run_roofer_smoke_host.sh ABSOLUTE_ARTIFACT_ROOT}"
TASK_REL="phase-payloads/p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1"
TASK_HOST="${ARTIFACT_ROOT_HOST}/${TASK_REL}"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
ROOFER_IMAGE_ID_EXPECTED="sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"
PROJECT_IMAGE="jointbuildgs:dev"
SOURCE_COMMIT="$(git -C "${REPO}" rev-parse HEAD)"

if [[ "${ARTIFACT_ROOT_HOST}" != /* || ! -d "${ARTIFACT_ROOT_HOST}" ]]; then
  echo "artifact root must be an existing absolute directory" >&2
  exit 2
fi
if [[ ! -f "${TASK_HOST}/control/execution_ledger_v1.json" ]]; then
  echo "execution ledger is missing" >&2
  exit 2
fi
OBSERVED_REPO_DIGEST="$(docker image inspect "${ROOFER_IMAGE}" --format '{{join .RepoDigests "\n"}}' | grep -Fx "${ROOFER_IMAGE}" | head -n 1)"
OBSERVED_IMAGE_ID="$(docker image inspect "${ROOFER_IMAGE}" --format '{{.Id}}')"
if [[ "${OBSERVED_REPO_DIGEST}" != "${ROOFER_IMAGE}" || "${OBSERVED_IMAGE_ID}" != "${ROOFER_IMAGE_ID_EXPECTED}" ]]; then
  echo "pinned Roofer image observation mismatch" >&2
  exit 2
fi

OBSERVED_PROJECT_IMAGE_ID="$(docker image inspect "${PROJECT_IMAGE}" --format '{{.Id}}')"
if [[ ! "${OBSERVED_PROJECT_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "project image ID is invalid" >&2
  exit 2
fi

# Authority is checked before any Roofer output or attempt marker is created.
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" \
  -v "${ARTIFACT_ROOT_HOST}:/artifacts/JointBuildGS:ro" \
  -w /workspace/JointBuildGS \
  "${OBSERVED_PROJECT_IMAGE_ID}" \
  python scripts/input_and_alignment/gate_s0/freeze_recovery_v1/run_freeze_recovery.py \
  --mode runtime-control \
  --source-commit "${SOURCE_COMMIT}" \
  --artifact-root /artifacts/JointBuildGS \
  --observed-project-image-id "${OBSERVED_PROJECT_IMAGE_ID}"

STAGE3_HOST="${TASK_HOST}/stage3"
PENDING_ATTEMPT="${STAGE3_HOST}/.roofer_smoke.pending"
SEALED_ATTEMPT="${STAGE3_HOST}/roofer_smoke_sealed"
QUARANTINED_ATTEMPT="${STAGE3_HOST}/.roofer_smoke.quarantine.1"

if [[ -d "${PENDING_ATTEMPT}" && -d "${SEALED_ATTEMPT}" ]]; then
  echo "both pending and sealed Roofer attempts exist" >&2
  exit 2
fi
if [[ -d "${PENDING_ATTEMPT}" ]]; then
  if [[ -f "${PENDING_ATTEMPT}/exit_code" \
        && -f "${PENDING_ATTEMPT}/runtime.log" \
        && -d "${PENDING_ATTEMPT}/output" \
        && "$(tr -d '[:space:]' <"${PENDING_ATTEMPT}/exit_code")" =~ ^[0-9]+$ ]]; then
    mv "${PENDING_ATTEMPT}" "${SEALED_ATTEMPT}"
    sync -f "${STAGE3_HOST}" || sync
  else
    if [[ -e "${QUARANTINED_ATTEMPT}" ]]; then
      echo "Roofer synthetic retry cap exhausted" >&2
      exit 2
    fi
    mv "${PENDING_ATTEMPT}" "${QUARANTINED_ATTEMPT}"
  fi
fi

if [[ ! -d "${SEALED_ATTEMPT}" ]]; then
  mkdir -p "${PENDING_ATTEMPT}/output"
  set +e
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "${STAGE3_HOST}/synthetic_class26.laz:/work/stage3/synthetic_class26.laz:ro" \
    -v "${STAGE3_HOST}/synthetic_r_derived.geojson:/work/stage3/synthetic_r_derived.geojson:ro" \
    -v "${PENDING_ATTEMPT}/output:/work/stage3/roofer_output" \
    -w /work \
    "${ROOFER_IMAGE}" \
    --id-attribute building_id --jobs 1 --srs EPSG:25832 \
    --bld-class 6 --grnd-class 2 --lod22 \
    stage3/synthetic_class26.laz \
    stage3/synthetic_r_derived.geojson \
    stage3/roofer_output \
    >"${PENDING_ATTEMPT}/runtime.log" 2>&1
  ROOFER_EXIT=$?
  set -e
  printf '%s\n' "${ROOFER_EXIT}" >"${PENDING_ATTEMPT}/.exit_code.pending"
  find "${PENDING_ATTEMPT}/output" -type f -exec sync -f {} +
  sync -f "${PENDING_ATTEMPT}/runtime.log" "${PENDING_ATTEMPT}/.exit_code.pending" || sync
  mv "${PENDING_ATTEMPT}/.exit_code.pending" "${PENDING_ATTEMPT}/exit_code"
  sync -f "${PENDING_ATTEMPT}" || sync
  mv "${PENDING_ATTEMPT}" "${SEALED_ATTEMPT}"
  sync -f "${STAGE3_HOST}" || sync
fi

if [[ ! -f "${SEALED_ATTEMPT}/exit_code" || ! -f "${SEALED_ATTEMPT}/runtime.log" || ! -d "${SEALED_ATTEMPT}/output" ]]; then
  echo "sealed Roofer attempt is incomplete" >&2
  exit 2
fi
ROOFER_EXIT="$(tr -d '[:space:]' <"${SEALED_ATTEMPT}/exit_code")"
if [[ ! "${ROOFER_EXIT}" =~ ^[0-9]+$ ]]; then
  echo "sealed Roofer exit code is invalid" >&2
  exit 2
fi

# The recorder gets only the exact task namespace read-write, not the artifact root.
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "${REPO}:/workspace/JointBuildGS:ro" \
  -v "${ARTIFACT_ROOT_HOST}:/artifacts/JointBuildGS:ro" \
  -v "${TASK_HOST}:/artifacts/JointBuildGS/${TASK_REL}:rw" \
  -w /workspace/JointBuildGS \
  "${OBSERVED_PROJECT_IMAGE_ID}" \
  python scripts/input_and_alignment/gate_s0/freeze_recovery_v1/run_freeze_recovery.py \
  --mode record-roofer-smoke \
  --artifact-root /artifacts/JointBuildGS \
  --roofer-exit-code "${ROOFER_EXIT}" \
  --observed-roofer-image "${OBSERVED_REPO_DIGEST}" \
  --observed-roofer-image-id "${OBSERVED_IMAGE_ID}" \
  --observed-project-image-id "${OBSERVED_PROJECT_IMAGE_ID}"
