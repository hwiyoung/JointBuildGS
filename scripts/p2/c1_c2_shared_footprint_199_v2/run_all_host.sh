#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_all_host.sh ARTIFACT_ROOT [REPLAY_LABEL]}"
replay_label="${2:-}"
project_image="jointbuildgs:dev"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
expected_project_id="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
expected_roofer_id="sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"
config_container="/workspace/JointBuildGS/configs/p2/c1_c2_shared_footprint_199_v2/run_all_v2.json"
canonical_task_rel="phase-payloads/p2/c1_c2_shared_footprint_199_v2/P2-C1-C2-SHARED-FOOTPRINT-199-ALL-INVOCATIONS-v2"
if [[ -n "${replay_label}" ]]; then
  [[ "${replay_label}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || { echo "invalid replay label" >&2; exit 2; }
  task_rel="phase-payloads/p2/c1_c2_shared_footprint_199_v2/P2-C1-C2-SHARED-FOOTPRINT-199-ALL-INVOCATIONS-v2-replay-${replay_label}"
else
  task_rel="${canonical_task_rel}"
fi
final_root="${artifact_root}/${task_rel}"
partial_root="${final_root}.partial"

[[ "${artifact_root}" == /* && -d "${artifact_root}" ]] || { echo "artifact root must be an existing absolute directory" >&2; exit 2; }
[[ "$(docker image inspect "${project_image}" --format '{{.Id}}')" == "${expected_project_id}" ]] || { echo "project image identity mismatch" >&2; exit 2; }
[[ "$(docker image inspect "${roofer_image}" --format '{{.Id}}')" == "${expected_roofer_id}" ]] || { echo "Roofer image identity mismatch" >&2; exit 2; }
[[ ! -e "${final_root}" ]] || { echo "final add-once namespace already exists" >&2; exit 2; }

project_python() {
  docker run --rm --network none --entrypoint /opt/conda/bin/python \
    --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
    -v "${partial_root}:/task:rw" \
    -w /workspace/JointBuildGS "${project_image}" "$@"
}

project_run() {
  project_python scripts/p2/c1_c2_shared_footprint_199_v1/run.py "$@"
}

if [[ ! -e "${partial_root}" ]]; then
  mkdir -p "${partial_root}"
  project_run prepare --output-root /task --artifact-root /artifacts/JointBuildGS --config "${config_container}"
else
  [[ -f "${partial_root}/control/prepared_v1.json" ]] || { echo "partial namespace is not resumable" >&2; exit 2; }
fi

invocation_total="$(( $(wc -l < "${partial_root}/freeze/execution_units_v1.tsv") - 1 ))"
[[ "${invocation_total}" -eq 398 ]] || { echo "all-invocations contract violated: ${invocation_total} != 398" >&2; exit 2; }
invocation_index=0
while IFS=$'\t' read -r operation_id work_relative; do
  [[ "${operation_id}" == "operation_unit_id" ]] && continue
  invocation_index=$((invocation_index + 1))
  work="${partial_root}/${work_relative}"
  if [[ -f "${work}/roofer_terminal_v1.json" ]]; then
    echo "[${invocation_index}/${invocation_total}] reuse terminal ${operation_id}"
    continue
  fi
  if [[ -e "${work}/runtime.log" || -e "${work}/out" ]]; then
    echo "unsealed Roofer state refuses duplicate execution: ${operation_id}" >&2
    exit 2
  fi
  mkdir "${work}/out"
  echo "[${invocation_index}/${invocation_total}] Roofer ${operation_id}"
  start_seconds="${SECONDS}"
  set +e
  timeout 600 docker run --rm --network none --cpus 2 --memory 8g --pids-limit 512 \
    --user "$(id -u):$(id -g)" -v "${work}:/work:rw" -w /work "${roofer_image}" \
    --id-attribute stable_id --jobs 1 --srs EPSG:25832 --bld-class 6 --grnd-class 2 --lod22 \
    input.las shared_footprint.geojson out >"${work}/runtime.log" 2>&1
  exit_code=$?
  set -e
  project_run record-terminal --output-root /task --operation-id "${operation_id}" \
    --exit-code "${exit_code}" --runtime-seconds "$((SECONDS - start_seconds))" >/dev/null
done <"${partial_root}/freeze/execution_units_v1.tsv"

project_run finalize --output-root /task --config "${config_container}"
audit_args=(
  scripts/p2/c1_c2_shared_footprint_199_v1/reproducibility_audit.py
  --task-root /task
  --config "${config_container}"
)
if [[ -n "${replay_label}" ]]; then
  reference_path="${artifact_root}/${canonical_task_rel}/control/reproducibility_geometry_manifest_v1.json"
  [[ -f "${reference_path}" ]] || { echo "canonical reproducibility reference is missing" >&2; exit 2; }
  audit_args+=(--reference "/artifacts/JointBuildGS/${canonical_task_rel}/control/reproducibility_geometry_manifest_v1.json")
fi
project_python "${audit_args[@]}"
mv -- "${partial_root}" "${final_root}"
echo "all-invocations shared-footprint C1/C2 199 complete: ${final_root}"
