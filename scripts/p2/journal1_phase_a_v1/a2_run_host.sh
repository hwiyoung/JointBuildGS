#!/usr/bin/env bash
# Journal1 Phase A / A2 host driver: E7 (ALS-only) and E8 (E2 ∪ ALS) through the
# sealed crop→SMRF→footprint-overlay→Roofer chain (199 buildings), then crops.
# Non-confirmatory technical development; scientific_verdict stays null.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: a2_run_host.sh ARTIFACT_ROOT}"
project_image="jointbuildgs:dev"
tools_image="jointbuildgs-p0-tools:t0"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
expected_project_id="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
expected_tools_id="sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"
expected_roofer_id="sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"
task_root="${artifact_root}/phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1"
a2_root="${task_root}/a2"

[[ "${artifact_root}" == /* && -d "${artifact_root}" ]] || { echo "artifact root must be an existing absolute directory" >&2; exit 2; }
[[ -d "${task_root}" ]] || { echo "Phase-A task namespace missing: ${task_root}" >&2; exit 2; }
[[ "$(docker image inspect "${project_image}" --format '{{.Id}}')" == "${expected_project_id}" ]] || { echo "project image identity mismatch" >&2; exit 2; }
[[ "$(docker image inspect "${tools_image}" --format '{{.Id}}')" == "${expected_tools_id}" ]] || { echo "tools image identity mismatch" >&2; exit 2; }
[[ "$(docker image inspect "${roofer_image}" --format '{{.Id}}')" == "${expected_roofer_id}" ]] || { echo "Roofer image identity mismatch" >&2; exit 2; }
mkdir -p "${a2_root}"

project_run() {
  docker run --rm --network none \
    --user "$(id -u):$(id -g)" --cpus 12 --memory 96g --pids-limit 4096 \
    -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
    -v "${a2_root}:/task:rw" \
    -w /workspace/JointBuildGS "${project_image}" "$@"
}

tools_run() {
  docker run --rm --network none --entrypoint /bin/sh \
    --user "$(id -u):$(id -g)" --cpus 12 --memory 96g --pids-limit 4096 \
    -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
    -v "${a2_root}:/task:rw" \
    -w /workspace/JointBuildGS "${tools_image}" -lc "$1"
}

if [[ ! -f "${a2_root}/control/prepared_a2_v1.json" ]]; then
  project_run python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 prepare \
    --output-root /task --artifact-root /artifacts/JointBuildGS
fi

for condition in E7 E8; do
  work="${a2_root}/work/${condition}"

  if [[ ! -f "${work}/fused_surface_receipt.json" ]]; then
    project_run python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 fuse \
      --output-root /task --artifact-root /artifacts/JointBuildGS --condition "${condition}"
  fi

  if [[ ! -f "${work}/classified_scene_receipt.json" ]]; then
    [[ ! -e "${work}/classified_scene.laz" ]] || { echo "unsealed classified scene refuses reuse: ${condition}" >&2; exit 2; }
    tools_run "pdal pipeline '/task/work/${condition}/classification_pipeline.json' >'/task/work/${condition}/classification.log' 2>&1"
    tools_run "python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 verify-classified --output-root /task --condition '${condition}'"
  fi

  if [[ ! -f "${work}/roofer_terminal.json" ]]; then
    [[ ! -e "${work}/roofer_output" ]] || { echo "unsealed Roofer output refuses duplicate execution: ${condition}" >&2; exit 2; }
    mkdir "${work}/roofer_output"
    start_seconds="${SECONDS}"
    set +e
    timeout 14400 docker run --rm --network none --cpus 12 --memory 64g --pids-limit 4096 \
      --user "$(id -u):$(id -g)" -v "${a2_root}:/task:rw" -w /task "${roofer_image}" \
      --id-attribute stable_id --jobs 1 \
      --box 690791.740 5335864.050 691154.650 5336353.850 \
      "work/${condition}/classified_scene.laz" freeze/shared_footprints.geojson \
      "work/${condition}/roofer_output" >"${work}/roofer.log" 2>&1
    exit_code=$?
    set -e
    tools_run "python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 record-roofer --output-root /task --condition '${condition}' --exit-code '${exit_code}' --runtime-seconds '$((SECONDS - start_seconds))'"
  fi
done

if [[ ! -f "${a2_root}/control/finalized_a2_v1.json" ]]; then
  tools_run "python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 finalize --output-root /task"
fi

for condition in E7 E8; do
  if [[ ! -f "${a2_root}/assets_roofer_input/${condition}/receipt.json" ]]; then
    project_run python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 crops \
      --output-root /task --condition "${condition}"
  fi
done

echo "A2 E7/E8 chain complete: ${a2_root}"
