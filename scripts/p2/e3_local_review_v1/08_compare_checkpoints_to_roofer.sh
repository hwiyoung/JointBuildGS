#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
task_rel="phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1"
task_root="${artifact_root}/${task_rel}"
training_run="${task_root}/runs/E3_LOCAL_4906982_2DGS_V6_DIST0_RESETOFF_30K/seed0"
local_task="${artifact_root}/phase-payloads/p2/e3_local_4906982_v1/P2-E3-LOCAL-4906982-2DGS-v6-dist0-resetoff-30k"
data_root="${local_task}/data/colmap_crop"
view_roles="${local_task}/control/view_roles.json"
logs_root="${local_task}/logs/checkpoint_surface_comparison"
dev_image="jointbuildgs:dev"
tools_image="jointbuildgs-p0-tools:t0"
roofer_image="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
footprint_host="${artifact_root}/phase-payloads/p2/c1_c2_shared_footprint_199_v3/P2-C1-C2-SHARED-FOOTPRINT-199-ORIGINAL-GLOBAL-v3-replay-20260806a/freeze/shared_footprints_199.geojson"
mkdir -p "${logs_root}"

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

extract_variant() {
  local variant="$1" run_name="$2" checkpoint="$3"
  local run_root="${task_root}/runs/${run_name}"
  if [[ -f "${run_root}/pointcloud/extraction_receipt.json" ]]; then
    echo "SKIP extraction ${variant}"
    return
  fi
  docker run --rm --network none --shm-size 16g --gpus "device=${JBGS_GPU_INDEX:-0}" \
    --user "$(id -u):$(id -g)" -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp \
    -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS" \
    -w /workspace/JointBuildGS "${dev_image}" python \
    scripts/p2/e1_e6_techdev_v1/extract_tsdf.py \
    --checkpoint "${checkpoint/"${artifact_root}"//artifacts/JointBuildGS}" \
    --data-root "${data_root/"${artifact_root}"//artifacts/JointBuildGS}" \
    --view-roles "${view_roles/"${artifact_root}"//artifacts/JointBuildGS}" \
    --output-root "/artifacts/JointBuildGS/${task_rel}/runs/${run_name}" \
    --condition "E3_LOCAL_4906982_${variant}" >"${logs_root}/extract_${variant}.log" 2>&1
}

roofer_variant() {
  local variant="$1" run_name="$2"
  local roofer_root="${task_root}/runs/${run_name}/roofer"
  if [[ -f "${roofer_root}/receipt.json" ]]; then
    echo "SKIP Roofer ${variant}"
    return
  fi
  run_tools python scripts/p2/e1_e6_techdev_v1/prepare_roofer.py prepare \
    --artifact-root /artifacts/JointBuildGS --run-name "${run_name}" \
    >"${logs_root}/roofer_${variant}_prepare.log" 2>&1
  if [[ ! -f "${roofer_root}/classified_scene.laz" ]]; then
    run_tools pdal pipeline "/artifacts/JointBuildGS/${task_rel}/runs/${run_name}/roofer/classification_pipeline.json" \
      >"${logs_root}/roofer_${variant}_classify.log" 2>&1
  fi
  run_tools python scripts/p2/e1_e6_techdev_v1/prepare_roofer.py verify \
    --artifact-root /artifacts/JointBuildGS --run-name "${run_name}" \
    >"${logs_root}/roofer_${variant}_verify.log" 2>&1
  mkdir -p "${roofer_root}/output"
  docker run --rm --network none --cpus 12 --memory 64g --pids-limit 4096 \
    --user "$(id -u):$(id -g)" -v "${task_root}:/task:rw" \
    -v "${footprint_host}:/task/shared_footprints_199.geojson:ro" \
    -w /task "${roofer_image}" --id-attribute stable_id --jobs 1 \
    --box 690791.740 5335864.050 691154.650 5336353.850 \
    "runs/${run_name}/roofer/classified_scene.laz" shared_footprints_199.geojson \
    "runs/${run_name}/roofer/output" >"${logs_root}/roofer_${variant}.log" 2>&1
  run_dev python scripts/p2/e1_e6_techdev_v1/prepare_roofer.py finalize \
    --artifact-root /artifacts/JointBuildGS --run-name "${run_name}" \
    >"${logs_root}/roofer_${variant}_finalize.log" 2>&1
}

selection="${local_task}/control/checkpoint_selection.json"
test -f "${selection}"
extract_variant BESTVAL_7K E3_LOCAL_4906982_BESTVAL_7K "${training_run}/ckpt/step_007000.pt"
extract_variant FINAL_30K E3_LOCAL_4906982_FINAL_30K "${training_run}/ckpt/final.pt"
roofer_variant BESTVAL_7K E3_LOCAL_4906982_BESTVAL_7K
roofer_variant FINAL_30K E3_LOCAL_4906982_FINAL_30K

run_dev python scripts/p2/e3_local_review_v1/register_viewer_variants.py \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  --selection "${selection/"${artifact_root}"//artifacts/JointBuildGS}" \
  --output "/artifacts/JointBuildGS/${task_rel}/viewer/e3_local_variants.json" \
  >"${logs_root}/viewer_register.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/prepare_viewer_pointclouds.py \
  --artifact-root /artifacts/JointBuildGS --task-root "/artifacts/JointBuildGS/${task_rel}" \
  >"${logs_root}/viewer_pointclouds.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/prepare_viewer_surface_meshes.py \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  >"${logs_root}/viewer_surface_meshes.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/build_viewer.py \
  --repository-root /workspace/JointBuildGS --artifact-root /artifacts/JointBuildGS \
  >"${logs_root}/viewer_build.log" 2>&1

echo "E3 local 4906982 7k/30k depth-fusion, Roofer, and 8876 viewer update complete."
