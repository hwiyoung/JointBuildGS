#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
task_rel="phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1"
task_root="${artifact_root}/${task_rel}"
local_rel="phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v8-dist0p1norm-resetoff-pilot7k"
local_task="${artifact_root}/${local_rel}"
training_rel="${task_rel}/runs/E3_LOCAL_4906982_2DGS_V8_DIST0P1NORM_RESETOFF_PILOT7K/seed0"
baseline_run="E3_LOCAL_4906982_DIST0P1_BESTVAL7K_BASELINE"
filtered_run="E3_LOCAL_4906982_DIST0P1_BESTVAL7K_CONSENSUS3"
logs="${local_task}/logs/fusion_compare"
dev_image="jointbuildgs:dev"
tools_image="jointbuildgs-p0-tools:t0"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
roofer_jobs="${ROOFER_JOBS:-12}"
footprint="${artifact_root}/phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/freeze/shared_footprints_199.geojson"
mkdir -p "${logs}"

run_dev() {
  docker run --rm --network none --shm-size 16g --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS" \
    -w /workspace/JointBuildGS "${dev_image}" "$@"
}

run_tools() {
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS" \
    -w /workspace/JointBuildGS "${tools_image}" "$@"
}

roofer_variant() {
  local run_name="$1" tag="$2" roofer_root="${task_root}/runs/${run_name}/roofer"
  if [[ -f "${roofer_root}/receipt.json" ]]; then
    echo "SKIP Roofer ${tag}"
    return
  fi
  run_tools python scripts/p2/e1_e6_techdev_v1/prepare_roofer.py prepare \
    --artifact-root /artifacts/JointBuildGS --run-name "${run_name}" >"${logs}/roofer_${tag}_prepare.log" 2>&1
  if [[ ! -f "${roofer_root}/classified_scene.laz" ]]; then
    run_tools pdal pipeline "/artifacts/JointBuildGS/${task_rel}/runs/${run_name}/roofer/classification_pipeline.json" \
      >"${logs}/roofer_${tag}_classify.log" 2>&1
  fi
  run_tools python scripts/p2/e1_e6_techdev_v1/prepare_roofer.py verify \
    --artifact-root /artifacts/JointBuildGS --run-name "${run_name}" >"${logs}/roofer_${tag}_verify.log" 2>&1
  mkdir -p "${roofer_root}/output"
  docker run --rm --network none --cpus 12 --memory 64g --pids-limit 4096 \
    --user "$(id -u):$(id -g)" -v "${task_root}:/task:rw" \
    -v "${footprint}:/task/shared_footprints_199.geojson:ro" -w /task "${roofer_image}" \
    --id-attribute stable_id --jobs "${roofer_jobs}" --box 690791.740 5335864.050 691154.650 5336353.850 \
    "runs/${run_name}/roofer/classified_scene.laz" shared_footprints_199.geojson \
    "runs/${run_name}/roofer/output" >"${logs}/roofer_${tag}.log" 2>&1
  run_dev python scripts/p2/e1_e6_techdev_v1/prepare_roofer.py finalize \
    --artifact-root /artifacts/JointBuildGS --run-name "${run_name}" >"${logs}/roofer_${tag}_finalize.log" 2>&1
}

for run_name in "${baseline_run}" "${filtered_run}"; do
  test -f "${task_root}/runs/${run_name}/pointcloud/extraction_receipt.json"
done
roofer_variant "${baseline_run}" baseline
roofer_variant "${filtered_run}" consensus3

extra_specs="${local_task}/control/distortion_viewer_specs.json"
run_dev python scripts/p2/e3_local_review_v1/make_distortion_viewer_specs.py \
  --selection "/artifacts/JointBuildGS/${local_rel}/control/checkpoint_selection.json" \
  --output "/artifacts/JointBuildGS/${local_rel}/control/distortion_viewer_specs.json" \
  >"${logs}/viewer_specs.log" 2>&1
run_dev python scripts/p2/e3_local_review_v1/register_viewer_variants.py \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  --selection /artifacts/JointBuildGS/phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k/control/checkpoint_selection.json \
  --extra-specs "${extra_specs/"${artifact_root}"//artifacts/JointBuildGS}" \
  --output "/artifacts/JointBuildGS/${task_rel}/viewer/e3_local_variants.json" \
  >"${logs}/viewer_register.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/prepare_viewer_pointclouds.py \
  --artifact-root /artifacts/JointBuildGS --task-root "/artifacts/JointBuildGS/${task_rel}" \
  >"${logs}/viewer_pointclouds.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/prepare_viewer_surface_meshes.py \
  --task-root "/artifacts/JointBuildGS/${task_rel}" >"${logs}/viewer_surface_meshes.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/build_viewer.py \
  --repository-root /workspace/JointBuildGS --artifact-root /artifacts/JointBuildGS \
  >"${logs}/viewer_build.log" 2>&1

echo "distortion 0.1 baseline/consensus3 Roofer and 8876 viewer update complete"
