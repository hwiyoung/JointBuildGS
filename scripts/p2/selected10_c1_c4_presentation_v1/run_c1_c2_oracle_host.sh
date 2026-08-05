#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_c1_c2_oracle_host.sh ARTIFACT_ROOT PROJECT_IMAGE SOURCE_COMMIT RUN_ID}"
project_image="${2:?missing project image}"
source_commit="${3:?missing source commit}"
run_id="${4:?missing run ID}"
task_rel="phase-payloads/p2/selected10_c1_c4_presentation_v1/P2-SELECTED10-C1-C2-ORACLE-PRESENTATION-v1"
final_root="${artifact_root}/${task_rel}"
partial_root="${final_root}.partial"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
expected_project_id="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
expected_roofer_id="sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"

[[ "${artifact_root}" == /* && -d "${artifact_root}" ]] || { echo "artifact root must be an existing absolute directory" >&2; exit 2; }
[[ "$(docker image inspect "${project_image}" --format '{{.Id}}')" == "${expected_project_id}" ]] || { echo "project image identity mismatch" >&2; exit 2; }
[[ "$(docker image inspect "${roofer_image}" --format '{{.Id}}')" == "${expected_roofer_id}" ]] || { echo "Roofer image identity mismatch" >&2; exit 2; }
[[ "$(git -C "${repo_root}" rev-parse HEAD)" == "${source_commit}" ]] || { echo "HEAD/source mismatch" >&2; exit 2; }
[[ -z "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]] || { echo "clean committed worktree required" >&2; exit 2; }
[[ ! -e "${final_root}" ]] || { echo "final add-once oracle namespace already exists" >&2; exit 2; }

project_run() {
  docker run --rm --network none --entrypoint /opt/conda/bin/python \
    --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
    -e PYTHONDONTWRITEBYTECODE=1 -e MPLCONFIGDIR=/tmp/jbgs-mpl-cache \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
    -v "${partial_root}:/task:rw" \
    -w /workspace/JointBuildGS "${project_image}" \
    scripts/p2/selected10_c1_c4_presentation_v1/c1_c2_oracle.py "$@"
}

failure_receipt() {
  local stage="$1"
  local exit_code="$2"
  if [[ ! -e "${partial_root}/control/failure_receipt_v1.json" ]]; then
    mkdir -p "${partial_root}/control"
    printf '{"schema":"jointbuildgs.p2.selected10_c1_c2_oracle.failure.v1","status":"FAILED_PRESERVED","stage":"%s","exit_code":%s,"source_commit":"%s","run_id":"%s","scientific_verdict":null}\n' \
      "${stage}" "${exit_code}" "${source_commit}" "${run_id}" >"${partial_root}/control/failure_receipt_v1.json"
  fi
}
current_stage="prepare"
trap 'code=$?; if (( code != 0 )); then failure_receipt "${current_stage}" "${code}"; fi' EXIT

if [[ ! -e "${partial_root}" ]]; then
  mkdir -p "${partial_root}"
  project_run prepare --output-root /task --artifact-root /artifacts/JointBuildGS
else
  [[ -f "${partial_root}/control/prepared_v1.json" && -f "${partial_root}/control/failure_receipt_v1.json" ]] || {
    echo "partial namespace is not the exact preserved failed run" >&2
    exit 2
  }
  current_stage="repair-freeze"
  project_run repair-freeze --output-root /task
fi

current_stage="roofer"
while IFS=$'\t' read -r operation_id work_relative; do
  [[ "${operation_id}" == "operation_unit_id" ]] && continue
  work="${partial_root}/${work_relative}"
  if [[ -e "${work}/roofer_terminal_v1.json" ]]; then
    continue
  fi
  if [[ -e "${work}/runtime.log" || -d "${work}/out" ]]; then
    mapfile -t recovered_outputs < <(find "${work}/out" -maxdepth 1 -type f -name '*.city.jsonl' -print 2>/dev/null | sort)
    if [[ -f "${work}/runtime.log" && "${#recovered_outputs[@]}" -eq 1 ]]; then
      project_run record-terminal --output-root /task --operation-id "${operation_id}" \
        --exit-code 0 --runtime-seconds 0
      continue
    fi
    echo "existing Roofer state refuses duplicate execution: ${operation_id}" >&2
    exit 2
  fi
  mkdir "${work}/out"
  start_seconds="${SECONDS}"
  set +e
  timeout 600 docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
    --user "$(id -u):$(id -g)" -v "${work}:/work:rw" -w /work "${roofer_image}" \
    --id-attribute stable_id --jobs 1 --srs EPSG:25832 --bld-class 6 --grnd-class 2 --lod22 \
    input.las gt_footprint_oracle.geojson out >"${work}/runtime.log" 2>&1
  exit_code=$?
  set -e
  project_run record-terminal --output-root /task --operation-id "${operation_id}" \
    --exit-code "${exit_code}" --runtime-seconds "$((SECONDS - start_seconds))"
done <"${partial_root}/freeze/execution_units_v1.tsv"

current_stage="render-finalize"
project_run render-finalize --output-root /task --artifact-root /artifacts/JointBuildGS \
  --source-commit "${source_commit}" --run-id "${run_id}"

current_stage="promote"
mv -- "${partial_root}" "${final_root}"
trap - EXIT
echo "selected10 C1/C2 oracle presentation complete: ${final_root}"
