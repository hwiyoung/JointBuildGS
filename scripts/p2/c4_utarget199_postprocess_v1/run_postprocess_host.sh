#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_postprocess_host.sh ARTIFACT_ROOT PROJECT_IMAGE SOURCE_COMMIT RUN_ID}"
project_image="${2:?missing project image}"
source_commit="${3:?missing source commit}"
run_id="${4:?missing run ID}"
task_rel="phase-payloads/p2/c4_utarget199_postprocess_v1/P2-C4-UTARGET199-POSTPROCESS-v1"
task_root="${artifact_root}/${task_rel}"
checkpoint_rel="phase-payloads/p2/c4_existing_als_v1/P2-C4-EXISTING-ALS-BOUNDED-TECHDEV-v1/run/c4_existing_als/seed0/ckpt/final.pt"
reference_rel="phase-payloads/p2/utarget199_contract_results_v1/P2-UTARGET199-CONTRACT-RESULTS-v1/freeze/utarget199_reference_cells_v1.jsonl"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
expected_project_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
start_seconds="${SECONDS}"
current_stage="host_preflight"

if [[ "$(docker image inspect "${project_image}" --format '{{.Id}}')" != "${expected_project_image}" ]]; then
  echo "project image identity mismatch" >&2
  exit 2
fi
if [[ "$(git -C "${repo_root}" rev-parse HEAD)" != "${source_commit}" ]]; then
  echo "HEAD/source authority mismatch" >&2
  exit 2
fi
if [[ -n "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "clean committed worktree required" >&2
  exit 2
fi
[[ ! -e "${task_root}" ]] || { echo "fresh add-once task namespace required" >&2; exit 2; }
for path in "${artifact_root}/${checkpoint_rel}" "${artifact_root}/${reference_rel}"; do
  [[ -f "${path}" && ! -L "${path}" ]] || { echo "exact input missing/non-regular: ${path}" >&2; exit 2; }
done

mkdir -p "${task_root}/control/torch_extensions" "${task_root}/control/cache"

project_run() {
  docker run --rm --network none --entrypoint python \
    --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
    -v "${task_root}:/task:rw" \
    -w /workspace/JointBuildGS "${project_image}" \
    scripts/p2/c4_utarget199_postprocess_v1/run_postprocess.py "$@"
}

record_failure() {
  local exit_code="$1"
  set +e
  project_run record-failure --output-root /task --stage "${current_stage}" \
    --exit-code "${exit_code}" --source-commit "${source_commit}" --run-id "${run_id}" >/dev/null
  set -e
}
trap 'failure_code=$?; record_failure "${failure_code}"; exit "${failure_code}"' ERR

current_stage="contract_preflight"
project_run preflight
current_stage="freeze_c4_geometry"
project_run prepare-condition --output-root /task \
  --checkpoint "/artifacts/JointBuildGS/${checkpoint_rel}" \
  --source-commit "${source_commit}" --run-id "${run_id}"
current_stage="associate_utarget199"
project_run associate --output-root /task \
  --current-uas-reference "/artifacts/JointBuildGS/${reference_rel}" \
  --source-commit "${source_commit}" --run-id "${run_id}"

current_stage="roofer_stage3"
while IFS=$'\t' read -r unit_id work_relative; do
  [[ "${unit_id}" == "operation_unit_id" ]] && continue
  work="${task_root}/${work_relative}"
  if [[ -f "${work}/roofer_terminal_v1.json" ]]; then
    project_run verify-terminal --output-root /task --unit-id "${unit_id}" >/dev/null
    continue
  fi
  if [[ -e "${work}/runtime.log" || -e "${work}/out" ]]; then
    echo "partial Roofer unit requires recovery namespace: ${unit_id}" >&2
    exit 2
  fi
  mkdir "${work}/out"
  begin="${SECONDS}"
  set +e
  timeout 600 docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
    --user "$(id -u):$(id -g)" -v "${work}:/work:rw" -w /work "${roofer_image}" \
    --id-attribute component_id --jobs 1 --srs EPSG:25832 --bld-class 6 --grnd-class 2 --lod22 \
    input.las r_derived.geojson out >"${work}/runtime.log" 2>&1
  exit_code=$?
  set -e
  project_run record-terminal --output-root /task --unit-id "${unit_id}" \
    --exit-code "${exit_code}" --runtime-seconds "$((SECONDS - begin))" >/dev/null
  if (( SECONDS - start_seconds > 43200 )); then
    echo "12-hour C4 postprocess cap exceeded" >&2
    exit 2
  fi
done <"${task_root}/freeze/execution_units_v1.tsv"

current_stage="metric_finalize"
project_run finalize --output-root /task --artifact-root /artifacts/JointBuildGS \
  --source-commit "${source_commit}" --run-id "${run_id}"

gpu_index=""
while IFS=, read -r index free; do
  index="${index// /}"
  free="${free// /}"
  if (( free >= 18000 )); then
    gpu_index="${index}"
    break
  fi
done < <(nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits)
[[ -n "${gpu_index}" ]] || { echo "no GPU satisfies 18 GiB render guard" >&2; exit 2; }

current_stage="c4_gs_render"
docker run --rm --network none --shm-size 8g --gpus "device=${gpu_index}" \
  --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
  -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 \
  -e XDG_CACHE_HOME=/task/control/cache \
  -e TORCH_EXTENSIONS_DIR=/task/control/torch_extensions \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
  -v "${task_root}:/task:rw" \
  -w /workspace/JointBuildGS "${project_image}" \
  python scripts/p2/c4_utarget199_postprocess_v1/render_gs.py \
    --output-root /task --artifact-root /artifacts/JointBuildGS \
    --checkpoint "/artifacts/JointBuildGS/${checkpoint_rel}" --device cuda

current_stage="qualitative_199"
docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
  -v "${task_root}:/task:rw" \
  -w /workspace/JointBuildGS "${project_image}" \
  scripts/p2/c4_utarget199_postprocess_v1/render_case_sheets.py \
    --task-root /task --artifact-root /artifacts/JointBuildGS

current_stage="seal_complete"
project_run complete --output-root /task
trap - ERR
echo "C4 U_target=199 postprocess complete: ${task_root}"
