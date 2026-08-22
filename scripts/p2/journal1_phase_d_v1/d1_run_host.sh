#!/usr/bin/env bash
# Phase D / D1 host driver: union-side delta-shift curve.
# Reruns the sealed training-free E7/E8 chains with a synthetic ALS offset
# (config run matrix), then evaluates each run on the confirmed 93 buildings.
# Non-confirmatory technical development; scientific_verdict stays null.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: d1_run_host.sh ARTIFACT_ROOT}"
project_image="jointbuildgs:dev"
tools_image="jointbuildgs-p0-tools:t0"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
expected_project_id="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
expected_tools_id="sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"
expected_roofer_id="sha256:9c980b97fba4c3fd30f5bb4afb8f2621be211d4e72e4333ea2053e8cd69b2dba"
phase_rel="phase-payloads/p2/journal1_phase_d_v1/P2-JOURNAL1-PHASE-D-v1"
phase_root="${artifact_root}/${phase_rel}"
cont_phase="/artifacts/JointBuildGS/${phase_rel}"
union_root="${phase_root}/union_curve"
config="${repo_root}/configs/p2/journal1_phase_d_v1/d1_union_curve_v1.json"
selection="${artifact_root}/phase-payloads/p2/journal1_phase_a_v1/P2-JOURNAL1-PHASE-A-v1/labels/selection_confirm_v1.json"

[[ "${artifact_root}" == /* && -d "${artifact_root}" ]] || { echo "artifact root must be an existing absolute directory" >&2; exit 2; }
[[ -f "${selection}" ]] || { echo "confirmed selection missing: ${selection}" >&2; exit 2; }
[[ "$(docker image inspect "${project_image}" --format '{{.Id}}')" == "${expected_project_id}" ]] || { echo "project image identity mismatch" >&2; exit 2; }
[[ "$(docker image inspect "${tools_image}" --format '{{.Id}}')" == "${expected_tools_id}" ]] || { echo "tools image identity mismatch" >&2; exit 2; }
[[ "$(docker image inspect "${roofer_image}" --format '{{.Id}}')" == "${expected_roofer_id}" ]] || { echo "Roofer image identity mismatch" >&2; exit 2; }
mkdir -p "${union_root}"

SEL93="$(python3 -c "import json; print(','.join(json.load(open('${selection}'))['effective_selected_ids']))")"

project_run() {
  docker run --rm --network none \
    --user "$(id -u):$(id -g)" --cpus 12 --memory 96g --pids-limit 4096 \
    -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
    -v "${phase_root}:${cont_phase}:rw" \
    -w /workspace/JointBuildGS "${project_image}" "$@"
}

tools_run() {
  docker run --rm --network none --entrypoint /bin/sh \
    --user "$(id -u):$(id -g)" --cpus 12 --memory 96g --pids-limit 4096 \
    -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
    -v "${phase_root}:${cont_phase}:rw" \
    -w /workspace/JointBuildGS "${tools_image}" -lc "$1"
}

while IFS='|' read -r label cond dx dz; do
  root_h="${union_root}/${label}"
  root_c="${cont_phase}/union_curve/${label}"
  work="${root_h}/work/${cond}"
  mkdir -p "${root_h}"
  echo "[D1] === ${label} (cond=${cond} dx=${dx} dz=${dz}) ==="

  if [[ ! -f "${root_h}/control/prepared_a2_v1.json" ]]; then
    project_run python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 prepare \
      --output-root "${root_c}" --artifact-root /artifacts/JointBuildGS
  fi

  if [[ ! -f "${work}/fused_surface_receipt.json" ]]; then
    project_run python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 fuse \
      --output-root "${root_c}" --artifact-root /artifacts/JointBuildGS \
      --condition "${cond}" --delta-xy-east-m "${dx}" --delta-z-m "${dz}"
  fi

  if [[ ! -f "${work}/classified_scene_receipt.json" ]]; then
    [[ ! -e "${work}/classified_scene.laz" ]] || { echo "unsealed classified scene refuses reuse: ${label}" >&2; exit 2; }
    tools_run "pdal pipeline '${root_c}/work/${cond}/classification_pipeline.json' >'${root_c}/work/${cond}/classification.log' 2>&1"
    tools_run "python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 verify-classified --output-root '${root_c}' --condition '${cond}'"
  fi

  if [[ ! -f "${work}/roofer_terminal.json" ]]; then
    [[ ! -e "${work}/roofer_output" ]] || { echo "unsealed Roofer output refuses duplicate execution: ${label}" >&2; exit 2; }
    mkdir "${work}/roofer_output"
    start_seconds="${SECONDS}"
    set +e
    timeout 14400 docker run --rm --network none --cpus 12 --memory 64g --pids-limit 4096 \
      --user "$(id -u):$(id -g)" -v "${root_h}:/task:rw" -w /task "${roofer_image}" \
      --id-attribute stable_id --jobs 1 \
      --box 690791.740 5335864.050 691154.650 5336353.850 \
      "work/${cond}/classified_scene.laz" freeze/shared_footprints.geojson \
      "work/${cond}/roofer_output" >"${work}/roofer.log" 2>&1
    exit_code=$?
    set -e
    tools_run "python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 record-roofer --output-root '${root_c}' --condition '${cond}' --exit-code '${exit_code}' --runtime-seconds '$((SECONDS - start_seconds))'"
  fi

  if [[ ! -f "${root_h}/control/finalized_a2_v1.json" ]]; then
    tools_run "python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 finalize --output-root '${root_c}' --conditions '${cond}'"
  fi

  if [[ ! -f "${root_h}/assets_roofer_input/${cond}/receipt.json" ]]; then
    project_run python -B -m scripts.p2.journal1_phase_a_v1.a2_build_e7_e8 crops \
      --output-root "${root_c}" --condition "${cond}"
  fi

  if [[ ! -f "${root_h}/evaluation/receipt.json" ]]; then
    project_run python -B scripts/p2/journal1_phase_d_v1/d1_eval_config.py \
      --run-root "${root_c}" --arm "${label}" --condition "${cond}"
    project_run python -B scripts/p2/journal1_phase_a_v1/geometry_eval.py \
      --config "${root_c}/control/eval_config.json" --arms "${label}" --buildings "${SEL93}"
  fi

  echo "[D1] ${label} complete"
done < <(python3 -c "
import json
cfg = json.load(open('${config}'))
for r in cfg['runs']:
    print(f\"{r['label']}|{r['condition']}|{r['dx']}|{r['dz']}\")
")

echo "D1 union curve complete: ${union_root}"
