#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

pilot_root="${prep_root}/semantic_gt_dense_scan_pilot_v1"
rgb_root="${prep_root}/semantic_gt_dense_scan_rgb_sam_pilot_v1"
raw_scan="/artifacts/JointBuildGS/phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz"
views=(
  DJI_20241217084253_0010_D.JPG
  DJI_20241217095525_0045_D.JPG
  DJI_20241217103641_0090_D.JPG
)

run_dev python scripts/p2/e1_e6_techdev_v1/make_semantic_dense_scan_pilot.py \
  --artifact-root /artifacts/JointBuildGS \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  --raw-scan "${raw_scan}" \
  --output-root "/artifacts/JointBuildGS/${task_rel}/prep/semantic_gt_dense_scan_pilot_v1" \
  --view-indices 0 58 116 \
  >"${logs_root}/06_semantic_dense_scan_pilot.log" 2>&1

docker run --rm --network none --shm-size 8g \
  --gpus "device=${JBGS_SEMANTIC_GPU_INDEX:-1}" \
  --user "$(id -u):$(id -g)" -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS "${dev_image}" python \
  scripts/p2/e1_e6_techdev_v1/make_semantic_rgb_sam_v2.py \
  --artifact-root /artifacts/JointBuildGS \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  --dense-root "/artifacts/JointBuildGS/${task_rel}/prep/semantic_gt_dense_scan_pilot_v1" \
  --output-root "/artifacts/JointBuildGS/${task_rel}/prep/semantic_gt_dense_scan_rgb_sam_pilot_v1" \
  --view-names "${views[@]}" \
  --sam-source /artifacts/JointBuildGS/results/tum_transfer/e5_s3b0/runtime/sam_vit_b/segment-anything \
  --sam-checkpoint /artifacts/JointBuildGS/results/tum_transfer/e5_s3b0/runtime/sam_vit_b/sam_vit_b_01ec64.pth \
  --device cuda >"${logs_root}/06_semantic_dense_scan_rgb_sam_pilot.log" 2>&1

run_dev python scripts/p2/e1_e6_techdev_v1/make_semantic_pilot_comparisons.py \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  --output-root "/artifacts/JointBuildGS/${task_rel}/prep/semantic_gt_dense_scan_pilot_comparisons_v1" \
  --view-names "${views[@]}" \
  >"${logs_root}/06_semantic_dense_scan_pilot_comparisons.log" 2>&1

printf 'Dense-scan semantic pilot complete: %s and %s\n' "${pilot_root}" "${rgb_root}"
