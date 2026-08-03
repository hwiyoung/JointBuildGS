#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_postprocess_host.sh ARTIFACT_ROOT PROJECT_IMAGE SOURCE_COMMIT RUN_ID}"
project_image="${2:?missing project image}"
source_commit="${3:?missing source commit}"
run_id="${4:?missing run ID}"
task_rel="phase-payloads/p2/c3_utarget199_postprocess_v1/P2-C3-UTARGET199-POSTPROCESS-v1"
task_root="${artifact_root}/${task_rel}"
training_rel="phase-payloads/p2/c1_c2_c3_utarget199_v1/P2-C1-C2-C3-UTARGET199-TORCH-CACHE-RECOVERY-v1"
training_root="${artifact_root}/${training_rel}"
reference_rel="phase-payloads/p2/utarget199_contract_results_v1/P2-UTARGET199-CONTRACT-RESULTS-v1/freeze/utarget199_reference_cells_v1.jsonl"
data_rel="phase-payloads/p0-audit/data/work/mvs/colmap_dense"
accepted_rel="artifacts/manifests/handoffs/P2-W2C-C3-UTARGET199-POSTPROCESS-v1/100-accepted.json"
packet_rel="docs/handoffs/P2_W2C_C3_UTARGET199_POSTPROCESS_v1.md"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
expected_project_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
start_seconds="${SECONDS}"

if [[ "$(docker image inspect "${project_image}" --format '{{.Id}}')" != "${expected_project_image}" ]]; then
  echo "project image identity mismatch" >&2
  exit 2
fi
timeout 300 git -C "${repo_root}" fetch origin main
if [[ "$(git -C "${repo_root}" rev-parse HEAD)" != "$(git -C "${repo_root}" rev-parse origin/main)" \
  || -n "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "HEAD/origin/source/clean authority mismatch" >&2
  exit 2
fi
if [[ "$(sed -n 's/^- source_commit: `\([0-9a-f]\{40\}\)`.*$/\1/p' "${repo_root}/${packet_rel}")" != "${source_commit}" ]]; then
  echo "packet source commit mismatch" >&2
  exit 2
fi
[[ -f "${repo_root}/${accepted_rel}" ]] || { echo "accepted receipt missing" >&2; exit 2; }
[[ ! -e "${task_root}" ]] || { echo "fresh add-once task namespace required" >&2; exit 2; }
for path in \
  "${training_root}/control/c3_pair_completion.json" \
  "${training_root}/c3/c3_1_sem/seed0/ckpt/final.pt" \
  "${training_root}/c3/c3_2_sem_depth/seed0/ckpt/final.pt" \
  "${artifact_root}/${reference_rel}"; do
  [[ -f "${path}" && ! -L "${path}" ]] || { echo "exact input missing/non-regular: ${path}" >&2; exit 2; }
done
[[ -d "${artifact_root}/${data_rel}" && ! -L "${artifact_root}/${data_rel}" ]] || { echo "exact common data root missing" >&2; exit 2; }

docker run --rm --network none --entrypoint python \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
  -w /workspace/JointBuildGS "${project_image}" \
  scripts/repository/validate_two_host_handoff.py "${accepted_rel}" \
    --repo . --artifact-root /artifacts/JointBuildGS --origin-ref origin/main --head-ref HEAD

mkdir -p "${task_root}/control/torch_extensions" "${task_root}/control/cache"

project_run() {
  docker run --rm --network none --entrypoint python \
    --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${task_root}:/task:rw" \
    -v "${training_root}:/training:ro" \
    -v "${artifact_root}/${reference_rel}:/inputs/reference_cells_v1.jsonl:ro" \
    -w /workspace/JointBuildGS "${project_image}" \
    scripts/p2/c3_utarget199_postprocess_v1/run_postprocess.py "$@"
}

project_run preflight
project_run prepare-condition --output-root /task --condition-id C3_1_SEM \
  --checkpoint /training/c3/c3_1_sem/seed0/ckpt/final.pt --source-commit "${source_commit}" --run-id "${run_id}"
project_run prepare-condition --output-root /task --condition-id C3_2_SEM_DEPTH \
  --checkpoint /training/c3/c3_2_sem_depth/seed0/ckpt/final.pt --source-commit "${source_commit}" --run-id "${run_id}"
project_run associate --output-root /task --reference-cells /inputs/reference_cells_v1.jsonl \
  --source-commit "${source_commit}" --run-id "${run_id}"

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
    echo "12-hour postprocess cap exceeded" >&2
    exit 2
  fi
done <"${task_root}/freeze/execution_units_v1.tsv"

project_run finalize --output-root /task --source-commit "${source_commit}" --run-id "${run_id}"

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

render_condition() {
  local condition_id="$1"
  local checkpoint_rel="$2"
  docker run --rm --network none --shm-size 8g --gpus "device=${gpu_index}" \
    --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
    -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp \
    -e XDG_CACHE_HOME=/task/control/cache \
    -e TORCH_EXTENSIONS_DIR=/task/control/torch_extensions \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${task_root}:/task:rw" \
    -v "${training_root}/${checkpoint_rel}:/checkpoint/final.pt:ro" \
    -v "${artifact_root}/${data_rel}:/render_inputs/${data_rel}:ro" \
    -w /workspace/JointBuildGS "${project_image}" \
    python scripts/p2/c3_utarget199_postprocess_v1/render_gs.py condition \
      --output-root /task --artifact-root /render_inputs --checkpoint /checkpoint/final.pt \
      --condition-id "${condition_id}" --device cuda
}

render_condition C3_1_SEM c3/c3_1_sem/seed0/ckpt/final.pt
render_condition C3_2_SEM_DEPTH c3/c3_2_sem_depth/seed0/ckpt/final.pt
docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" --cpus 2 --memory 8g \
  -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${task_root}:/task:rw" \
  -w /workspace/JointBuildGS "${project_image}" \
  scripts/p2/c3_utarget199_postprocess_v1/render_gs.py finalize --output-root /task

docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${task_root}:/task:rw" \
  -v "${training_root}:/training:ro" -w /workspace/JointBuildGS "${project_image}" \
  scripts/p2/c3_utarget199_postprocess_v1/render_case_sheets.py \
    --task-root /task --checkpoint-root /training

project_run complete --output-root /task
echo "C3 U_target=199 postprocess complete: ${task_root}"
