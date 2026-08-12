#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_host.sh ARTIFACT_ROOT [GPU_INDEX]}"
gpu_index="${2:-0}"
project_image="jointbuildgs:dev"
tools_image="jointbuildgs-p0-tools:t0"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
expected_project_id="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
expected_tools_id="sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"
expected_roofer_id="sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"
config_container="/workspace/JointBuildGS/configs/p2/e4_e6_redesign_s3b_v1/run_v1.json"
task_name="P2-E4-E6-REDESIGN-S3B-v1"
task_rel="phase-payloads/p2/e4_e6_redesign_s3b_v1/${task_name}"
final_root="${artifact_root}/${task_rel}"
partial_root="${final_root}.partial"

[[ "${artifact_root}" == /* && -d "${artifact_root}" ]] || { echo "artifact root must be an existing absolute directory" >&2; exit 2; }
[[ "$(docker image inspect "${project_image}" --format '{{.Id}}')" == "${expected_project_id}" ]] || { echo "project image identity mismatch" >&2; exit 2; }
[[ "$(docker image inspect "${tools_image}" --format '{{.Id}}')" == "${expected_tools_id}" ]] || { echo "tools image identity mismatch" >&2; exit 2; }
[[ "$(docker image inspect "${roofer_image}" --format '{{.Id}}')" == "${expected_roofer_id}" ]] || { echo "Roofer image identity mismatch" >&2; exit 2; }
[[ ! -e "${final_root}" ]] || { echo "final add-once namespace already exists" >&2; exit 2; }
mkdir -p "${partial_root}"

project_run() {
  docker run --rm --network none --gpus "device=${gpu_index}" --shm-size 8g \
    --user "$(id -u):$(id -g)" --cpus 12 --memory 96g --pids-limit 4096 \
    -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
    -e TORCH_EXTENSIONS_DIR=/task/control/torch_extensions \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
    -v "${partial_root}:/task:rw" \
    -w /workspace/JointBuildGS "${project_image}" "$@"
}

tools_run() {
  docker run --rm --network none --entrypoint /bin/sh \
    --user "$(id -u):$(id -g)" --cpus 12 --memory 96g --pids-limit 4096 \
    -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
    -v "${partial_root}:/task:rw" \
    -w /workspace/JointBuildGS "${tools_image}" -lc "$1"
}

if [[ ! -f "${partial_root}/control/prepared_v1.json" ]]; then
  tools_run "python -B -m scripts.p2.e4_e6_redesign_s3b_v1.run --config '${config_container}' prepare --output-root /task --artifact-root /artifacts/JointBuildGS --repo-root /workspace/JointBuildGS --scope full199"
fi
mkdir -p "${partial_root}/control/torch_extensions"

for condition_id in E3_GS_image E4_V2_STATIC E5_V2_F1; do
  work="${partial_root}/work/${condition_id}"

  if [[ ! -f "${work}/fused_surface_receipt.json" ]]; then
    project_run python -B -m scripts.p2.e4_e6_redesign_s3b_v1.run \
      --config "${config_container}" fuse --output-root /task \
      --artifact-root /artifacts/JointBuildGS --repo-root /workspace/JointBuildGS \
      --condition-id "${condition_id}" --device cuda
  fi

  if [[ ! -f "${work}/classified_scene_receipt.json" ]]; then
    [[ ! -e "${work}/classified_scene.laz" ]] || { echo "unsealed classified scene refuses reuse" >&2; exit 2; }
    tools_run "pdal pipeline '/task/work/${condition_id}/classification_pipeline.json' >'/task/work/${condition_id}/classification.log' 2>&1"
    tools_run "python -B -m scripts.p2.e4_e6_redesign_s3b_v1.run --config '${config_container}' verify-classified --output-root /task --condition-id '${condition_id}'"
  fi

  if [[ ! -f "${work}/roofer_terminal.json" ]]; then
    [[ ! -e "${work}/roofer_output" ]] || { echo "unsealed Roofer output refuses duplicate execution" >&2; exit 2; }
    mkdir "${work}/roofer_output"
    start_seconds="${SECONDS}"
    set +e
    timeout 14400 docker run --rm --network none --cpus 12 --memory 64g --pids-limit 4096 \
      --user "$(id -u):$(id -g)" -v "${partial_root}:/task:rw" -w /task "${roofer_image}" \
      --id-attribute stable_id --jobs 1 \
      --box 690791.740 5335864.050 691154.650 5336353.850 \
      "work/${condition_id}/classified_scene.laz" freeze/shared_footprints.geojson \
      "work/${condition_id}/roofer_output" >"${work}/roofer.log" 2>&1
    exit_code=$?
    set -e
    tools_run "python -B -m scripts.p2.e4_e6_redesign_s3b_v1.run --config '${config_container}' record-roofer --output-root /task --condition-id '${condition_id}' --exit-code '${exit_code}' --runtime-seconds '$((SECONDS - start_seconds))'"
  fi
done

tools_run "python -B -m scripts.p2.e4_e6_redesign_s3b_v1.run --config '${config_container}' finalize --output-root /task"
mv -- "${partial_root}" "${final_root}"
echo "S3 shared-footprint Roofer complete: ${final_root}"
