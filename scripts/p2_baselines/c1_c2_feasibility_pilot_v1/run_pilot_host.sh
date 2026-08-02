#!/usr/bin/env bash
set -euo pipefail

# Host orchestrator. It mounts only exact frozen files and a task-owned output
# directory. Validation/held-out roots and the artifact root itself are never
# mounted into either container.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_ROOT="${1:?usage: run_pilot_host.sh ABS_ARTIFACT_ROOT PROJECT_IMAGE_ID SOURCE_COMMIT RUN_ID}"
PROJECT_IMAGE_ID="${2:?missing accepted project image ID}"
SOURCE_COMMIT="${3:?missing accepted source commit}"
RUN_ID="${4:?missing immutable run ID}"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
TASK_REL="phase-payloads/p2-baselines/c1_c2_feasibility_pilot_v1/P2-C1-C2-FEASIBILITY-PILOT-v1"
TASK_ROOT="${ARTIFACT_ROOT}/${TASK_REL}"
FREEZE_REL="phase-payloads/p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1"
R1_REL="phase-payloads/p0-audit/data/work/gate_s0/uas_reference_coverage_r1_v1/P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1"
C1_GRID="${ARTIFACT_ROOT}/${FREEZE_REL}/reference/c1_grid_v1.npz"
C1_CHECKPOINT="${ARTIFACT_ROOT}/${FREEZE_REL}/checkpoints/050-c1_reference_frozen_pre_c5.json"
C2_PLY="${ARTIFACT_ROOT}/${FREEZE_REL}/common/mvs_class26_v1.ply"
C2_CHECKPOINT="${ARTIFACT_ROOT}/${FREEZE_REL}/checkpoints/030-dense_mvs_and_gravity.json"
REFERENCE_CELLS="${ARTIFACT_ROOT}/${R1_REL}/reference/reference_candidate_cells_v1.csv"
ACCEPTED_RECEIPT_REL="artifacts/manifests/handoffs/P2-W2C-C1-C2-FEASIBILITY-PILOT-v1/100-accepted.json"
PACKET_REL="docs/handoffs/P2_W2C_C1_C2_FEASIBILITY_PILOT_v1.md"
START_SECONDS="${SECONDS}"

if [[ "${ARTIFACT_ROOT}" != /* || ! -d "${ARTIFACT_ROOT}" ]]; then
  echo "artifact root must be an existing absolute directory" >&2
  exit 2
fi
if [[ ! "${PROJECT_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ || ! "${SOURCE_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "project image/source commit identity is invalid" >&2
  exit 2
fi

# Authority is proven before any scientific file stat and before TASK_ROOT is
# created. The artifact-root mount here is exclusive to the canonical receipt
# validator; scientific project runs below receive only exact file mounts.
git -C "${REPO}" fetch origin main
HEAD_SHA="$(git -C "${REPO}" rev-parse HEAD)"
ORIGIN_SHA="$(git -C "${REPO}" rev-parse origin/main)"
PACKET_SOURCE_COMMIT="$(sed -n 's/^- source_commit: `\([0-9a-f]\{40\}\)`.*$/\1/p' "${REPO}/${PACKET_REL}")"
if [[ "${HEAD_SHA}" != "${ORIGIN_SHA}" || "${PACKET_SOURCE_COMMIT}" != "${SOURCE_COMMIT}" || -n "$(git -C "${REPO}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "HEAD/origin/source or clean-state authority mismatch" >&2
  exit 2
fi
if ! git -C "${REPO}" merge-base --is-ancestor "${SOURCE_COMMIT}" "${HEAD_SHA}"; then
  echo "packet source commit is not an ancestor of accepted HEAD" >&2
  exit 2
fi
if [[ ! -f "${REPO}/${ACCEPTED_RECEIPT_REL}" ]]; then
  echo "exact 100-accepted receipt is missing" >&2
  exit 2
fi
if ! grep -Fxq -- '- status: `APPROVED_FOR_EXECUTION`' "${REPO}/${PACKET_REL}" || \
   ! grep -Fxq -- '- user_approval: `APPROVED_FOR_EXECUTION`' "${REPO}/${PACKET_REL}"; then
  echo "packet is not explicitly activated for execution" >&2
  exit 2
fi
docker run --rm --network none \
  -v "${REPO}:/workspace/JointBuildGS:ro" \
  -v "${ARTIFACT_ROOT}:/artifacts/JointBuildGS:ro" \
  -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  python scripts/repository/validate_two_host_handoff.py "${ACCEPTED_RECEIPT_REL}" \
    --repo . --origin-ref origin/main --head-ref HEAD --artifact-root /artifacts/JointBuildGS
docker run --rm --network none -e EXPECTED_PROJECT_IMAGE_ID="${PROJECT_IMAGE_ID}" \
  -v "${REPO}:/workspace/JointBuildGS:ro" -w /workspace/JointBuildGS "${PROJECT_IMAGE_ID}" \
  python -c 'import json,os; p=json.load(open("artifacts/manifests/handoffs/P2-W2C-C1-C2-FEASIBILITY-PILOT-v1/100-accepted.json")); assert p["handoff_id"]=="P2-W2C-C1-C2-FEASIBILITY-PILOT-v1" and p["task_id"]=="P2-C1-C2-FEASIBILITY-PILOT-v1"; assert p["state"]=="accepted" and p["direction"]=="work_to_experiment"; assert p["sender_role"]=="work_host" and p["receiver_role"]=="experiment_host"; assert p["receiver_ack"]["role"]=="experiment_host" and p["receiver_ack"]["status"]=="accepted"; assert p["transport"]["exclusive_writer_ack"] is True; assert p["verification"]["docker_image_digest"]==os.environ["EXPECTED_PROJECT_IMAGE_ID"]'
for exact_input in "${C1_GRID}" "${C1_CHECKPOINT}" "${C2_PLY}" "${C2_CHECKPOINT}" "${REFERENCE_CELLS}"; do
  if [[ ! -f "${exact_input}" || -L "${exact_input}" ]]; then
    echo "exact frozen input missing or symlinked: ${exact_input}" >&2
    exit 2
  fi
done
mkdir -p "${TASK_ROOT}"

project_run() {
  docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
    --user "$(id -u):$(id -g)" \
    -v "${REPO}:/workspace/JointBuildGS:ro" \
    -v "${TASK_ROOT}:/pilot_output:rw" \
    -w /workspace/JointBuildGS \
    "${PROJECT_IMAGE_ID}" \
    python scripts/p2_baselines/c1_c2_feasibility_pilot_v1/run_pilot.py "$@"
}

project_science_prepare() {
  docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
    --user "$(id -u):$(id -g)" \
    -v "${REPO}:/workspace/JointBuildGS:ro" \
    -v "${TASK_ROOT}:/pilot_output:rw" \
    -v "${C1_GRID}:/pilot_inputs/c1/c1_grid_v1.npz:ro" \
    -v "${C1_CHECKPOINT}:/pilot_inputs/attestation/050-c1_reference_frozen_pre_c5.json:ro" \
    -v "${C2_PLY}:/pilot_inputs/c2/mvs_class26_v1.ply:ro" \
    -v "${C2_CHECKPOINT}:/pilot_inputs/attestation/030-dense_mvs_and_gravity.json:ro" \
    -v "${REFERENCE_CELLS}:/pilot_inputs/reference/reference_candidate_cells_v1.csv:ro" \
    -w /workspace/JointBuildGS \
    "${PROJECT_IMAGE_ID}" \
    python scripts/p2_baselines/c1_c2_feasibility_pilot_v1/run_pilot.py prepare-scientific \
      --output-root /pilot_output \
      --c1-grid /pilot_inputs/c1/c1_grid_v1.npz \
      --c1-checkpoint /pilot_inputs/attestation/050-c1_reference_frozen_pre_c5.json \
      --c2-ply /pilot_inputs/c2/mvs_class26_v1.ply \
      --c2-checkpoint /pilot_inputs/attestation/030-dense_mvs_and_gravity.json \
      --reference-cells /pilot_inputs/reference/reference_candidate_cells_v1.csv \
      --source-commit "${SOURCE_COMMIT}" --run-id "${RUN_ID}" \
      --handoff-id P2-W2C-C1-C2-FEASIBILITY-PILOT-v1 \
      --accepted-receipt "/workspace/JointBuildGS/${ACCEPTED_RECEIPT_REL}" \
      --accepted-commit "${HEAD_SHA}" --project-image-id "${PROJECT_IMAGE_ID}" \
      --artifact-root-token artifact://JointBuildGS
}

# The first gate reads zero scientific bytes.
project_run preflight
project_run prepare-synthetic --output-root /pilot_output
mkdir -p "${TASK_ROOT}/smoke/work/out"
set +e
timeout 600 docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
  --user "$(id -u):$(id -g)" \
  -v "${TASK_ROOT}/smoke/work:/work:rw" -w /work \
  "${ROOFER_IMAGE}" \
  --id-attribute component_id --jobs 1 --srs EPSG:25832 --bld-class 6 --grnd-class 2 --lod22 \
  input.las r_derived.geojson out >"${TASK_ROOT}/smoke/work/runtime.log" 2>&1
SMOKE_EXIT=$?
set -e
project_run verify-synthetic --output-root /pilot_output --roofer-output /pilot_output/smoke/work/out --exit-code "${SMOKE_EXIT}"

# Only a passed smoke permits the exact scientific mounts above to be opened.
project_science_prepare

while IFS=$'\t' read -r unit_id work_relative; do
  if [[ "${unit_id}" == "operation_unit_id" ]]; then
    continue
  fi
  for _attempt_loop in 1 2; do
    mapfile -t decision < <(project_run next-attempt --output-root /pilot_output --unit-id "${unit_id}" --machine-lines)
    if [[ "${decision[0]}" == "SKIP_COMPLETED" ]]; then
      break
    fi
    if [[ "${decision[0]}" != "RUN" || ! "${decision[1]}" =~ ^[12]$ ]]; then
      echo "invalid next-attempt decision for ${unit_id}" >&2
      exit 2
    fi
    attempt_number="${decision[1]}"
    work_host="${TASK_ROOT}/${work_relative}"
    mkdir -p "${work_host}/out"
    attempt_start="${SECONDS}"
    set +e
    timeout 600 docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
      --user "$(id -u):$(id -g)" \
      -v "${work_host}:/work:rw" -w /work \
      "${ROOFER_IMAGE}" \
      --id-attribute component_id --jobs 1 --srs EPSG:25832 --bld-class 6 --grnd-class 2 --lod22 \
      input.las r_derived.geojson out >"${work_host}/runtime.attempt_${attempt_number}.log" 2>&1
    roofer_exit=$?
    set -e
    runtime_seconds=$((SECONDS - attempt_start))
    set +e
    project_run record-attempt --output-root /pilot_output --unit-id "${unit_id}" \
      --attempt-number "${attempt_number}" --exit-code "${roofer_exit}" --runtime-seconds "${runtime_seconds}" \
      --peak-memory-unavailable-reason ROOFER_IMAGE_GNU_TIME_UNAVAILABLE_VERIFIED_IMMUTABLE_IMAGE
    record_exit=$?
    set -e
    if [[ "${record_exit}" -eq 75 ]]; then
      continue
    fi
    if [[ "${record_exit}" -ne 0 ]]; then
      exit "${record_exit}"
    fi
    break
  done
  if (( SECONDS - START_SECONDS > 43200 )); then
    echo "hard 12-hour task cap exceeded" >&2
    exit 2
  fi
  output_bytes="$(du -sb -- "${TASK_ROOT}" | cut -f1)"
  if (( output_bytes > 100000000000 )); then
    echo "hard 100GB output cap exceeded" >&2
    exit 2
  fi
done <"${TASK_ROOT}/freeze/execution_units_v1.tsv"

project_run finalize --output-root /pilot_output
echo "C1/C2 unique Roofer operations and exact 102-row descriptive scoring are complete."
