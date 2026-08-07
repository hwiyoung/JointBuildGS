#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

anchor_root="${prep_root}/semantic_mvs_anchor_pilot_v1"
raw_root="${prep_root}/semantic_mvs_raw_pilot_v1"
rgb_root="${prep_root}/semantic_mvs_raw_rgb_sam_pilot_v1"
mvs_dense="/artifacts/JointBuildGS/phase-payloads/p0-audit/data/work/mvs/dim/dim_v1.laz"
classified="${anchor_root}/current_mvs_csf_voxel010.laz"
views=(
  DJI_20241217084253_0010_D.JPG
  DJI_20241217095525_0045_D.JPG
  DJI_20241217103641_0090_D.JPG
)

mkdir -p "${anchor_root}"
if [[ ! -f "${classified}" ]]; then
  pipeline="${anchor_root}/csf_pipeline.json"
  sed \
    -e "s|__INPUT__|${mvs_dense}|" \
    -e "s|__OUTPUT__|/artifacts/JointBuildGS/${task_rel}/prep/semantic_mvs_anchor_pilot_v1/current_mvs_csf_voxel010.laz|" \
    scripts/p2/e1_e6_techdev_v1/semantic_mvs_csf_pipeline.template.json >"${pipeline}"
  run_tools pdal pipeline "/artifacts/JointBuildGS/${task_rel}/prep/semantic_mvs_anchor_pilot_v1/csf_pipeline.json" \
    >"${logs_root}/06_semantic_mvs_csf.log" 2>&1
fi

run_dev python scripts/p2/e1_e6_techdev_v1/make_semantic_gt_dense.py \
  --artifact-root /artifacts/JointBuildGS \
  --classified-scan "/artifacts/JointBuildGS/${task_rel}/prep/semantic_mvs_anchor_pilot_v1/current_mvs_csf_voxel010.laz" \
  --output-root "/artifacts/JointBuildGS/${task_rel}/prep/semantic_mvs_anchor_pilot_v1" \
  --view-indices 0 58 116 \
  --source-voxel-m 0.10 \
  --source-role CURRENT_IMAGE_DERIVED_MVS_DENSE_PSEUDO_GT_ANCHOR \
  >"${logs_root}/06_semantic_mvs_anchor.log" 2>&1

run_dev python scripts/p2/e1_e6_techdev_v1/make_semantic_dense_scan_pilot.py \
  --artifact-root /artifacts/JointBuildGS \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  --raw-scan "${mvs_dense}" \
  --output-root "/artifacts/JointBuildGS/${task_rel}/prep/semantic_mvs_raw_pilot_v1" \
  --anchor-root "/artifacts/JointBuildGS/${task_rel}/prep/semantic_mvs_anchor_pilot_v1/surface_cache" \
  --view-indices 0 58 116 \
  --label-transfer-max-distance-m 0.20 \
  --anchor-source-voxel-m 0.10 \
  --source-role CURRENT_IMAGE_DERIVED_RAW_MVS_DENSE_PSEUDO_GT_PILOT \
  --controlled-change PROJECT_RAW_MVS_DENSE_AFTER_NEAREST_MVS_ANCHOR_LABEL_TRANSFER_NO_LIDAR_INPUT \
  >"${logs_root}/06_semantic_mvs_raw.log" 2>&1

docker run --rm --network none --shm-size 8g \
  --gpus "device=${JBGS_SEMANTIC_GPU_INDEX:-1}" \
  --user "$(id -u):$(id -g)" -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS "${dev_image}" python \
  scripts/p2/e1_e6_techdev_v1/make_semantic_rgb_sam_v2.py \
  --artifact-root /artifacts/JointBuildGS \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  --dense-root "/artifacts/JointBuildGS/${task_rel}/prep/semantic_mvs_raw_pilot_v1" \
  --output-root "/artifacts/JointBuildGS/${task_rel}/prep/semantic_mvs_raw_rgb_sam_pilot_v1" \
  --view-names "${views[@]}" \
  --sam-source /artifacts/JointBuildGS/results/tum_transfer/e5_s3b0/runtime/sam_vit_b/segment-anything \
  --sam-checkpoint /artifacts/JointBuildGS/results/tum_transfer/e5_s3b0/runtime/sam_vit_b/sam_vit_b_01ec64.pth \
  --device cuda >"${logs_root}/06_semantic_mvs_rgb_sam.log" 2>&1

printf 'MVS semantic pseudo-GT pilot complete: %s %s %s\n' "${anchor_root}" "${raw_root}" "${rgb_root}"
