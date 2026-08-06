#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_original_global_host.sh ARTIFACT_ROOT [REPLAY_LABEL]}"
replay_label="${2:-}"
tools_image="jointbuildgs-p0-tools:t0"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
expected_tools_id="sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"
expected_roofer_id="sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"
config_container="/workspace/JointBuildGS/configs/p2/c1_c2_shared_footprint_199_v3/original_global_v3.json"
canonical_task_rel="phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3"

if [[ -n "${replay_label}" ]]; then
  [[ "${replay_label}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || { echo "invalid replay label" >&2; exit 2; }
  task_rel="${canonical_task_rel}-replay-${replay_label}"
else
  task_rel="${canonical_task_rel}"
fi
final_root="${artifact_root}/${task_rel}"
partial_root="${final_root}.partial"

[[ "${artifact_root}" == /* && -d "${artifact_root}" ]] || { echo "artifact root must be an existing absolute directory" >&2; exit 2; }
[[ "$(docker image inspect "${tools_image}" --format '{{.Id}}')" == "${expected_tools_id}" ]] || { echo "p0-tools image identity mismatch" >&2; exit 2; }
[[ "$(docker image inspect "${roofer_image}" --format '{{.Id}}')" == "${expected_roofer_id}" ]] || { echo "Roofer image identity mismatch" >&2; exit 2; }
[[ ! -e "${final_root}" ]] || { echo "final add-once namespace already exists" >&2; exit 2; }

tools_run() {
  docker run --rm --network none --entrypoint /bin/sh \
    --user "$(id -u):$(id -g)" --cpus 12 --memory 64g --pids-limit 4096 \
    -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
    -v "${partial_root}:/task:rw" \
    -w /workspace/JointBuildGS "${tools_image}" -lc "$1"
}

if [[ ! -e "${partial_root}" ]]; then
  mkdir -p "${partial_root}"
  tools_run "python scripts/p2/c1_c2_shared_footprint_199_v3/run.py prepare --output-root /task --artifact-root /artifacts/JointBuildGS --config '${config_container}'"
else
  [[ -f "${partial_root}/control/prepared_v3.json" ]] || { echo "partial namespace is not resumable" >&2; exit 2; }
fi

for method in C1_L_upper C2_MVS; do
  work="${partial_root}/work/${method}"
  if [[ ! -f "${work}/classified_scene_receipt.json" ]]; then
    [[ ! -e "${work}/classified_scene.laz" ]] || { echo "unsealed classified scene refuses reuse: ${method}" >&2; exit 2; }
    tools_run "pdal pipeline '/task/work/${method}/classification_pipeline.json' >'/task/work/${method}/classification.log' 2>&1"
    tools_run "python scripts/p2/c1_c2_shared_footprint_199_v3/run.py verify-classified --output-root /task --method '${method}' --config '${config_container}'"
  fi
done

for method in C1_L_upper C2_MVS; do
  work="${partial_root}/work/${method}"
  if [[ -f "${work}/roofer_terminal.json" ]]; then
    echo "reuse Roofer terminal: ${method}"
    continue
  fi
  [[ ! -e "${work}/roofer_output" ]] || { echo "unsealed Roofer output refuses duplicate execution: ${method}" >&2; exit 2; }
  mkdir "${work}/roofer_output"
  echo "Roofer original-global: ${method}"
  start_seconds="${SECONDS}"
  set +e
  timeout 14400 docker run --rm --network none --cpus 12 --memory 64g --pids-limit 4096 \
    --user "$(id -u):$(id -g)" -v "${partial_root}:/task:rw" -w /task "${roofer_image}" \
    --id-attribute stable_id --jobs 1 \
    --box 690791.740 5335864.050 691154.650 5336353.850 \
    "work/${method}/classified_scene.laz" freeze/shared_footprints_199.geojson \
    "work/${method}/roofer_output" >"${work}/roofer.log" 2>&1
  exit_code=$?
  set -e
  tools_run "python scripts/p2/c1_c2_shared_footprint_199_v3/run.py record-roofer --output-root /task --method '${method}' --exit-code '${exit_code}' --runtime-seconds '$((SECONDS - start_seconds))'"
done

tools_run "python scripts/p2/c1_c2_shared_footprint_199_v3/run.py finalize --output-root /task --config '${config_container}'"
mv -- "${partial_root}" "${final_root}"
echo "original-global C1/C2 Roofer complete: ${final_root}"
