#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
semantic_root="${prep_root}/semantic_gt"
classified="${semantic_root}/current_eval_csf_voxel025.laz"
mkdir -p "${semantic_root}"
if [[ ! -f "${classified}" ]]; then
  pipeline="${semantic_root}/csf_pipeline.json"
  printf '%s\n' '{"pipeline":[' \
    '{"type":"readers.las","filename":"/artifacts/JointBuildGS/phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz","override_srs":"EPSG:25832"},' \
    '{"type":"filters.crop","bounds":"([690791.740,691154.650],[5335864.050,5336353.850])"},' \
    '{"type":"filters.csf"},' \
    '{"type":"filters.voxelcenternearestneighbor","cell":0.25},' \
    '{"type":"writers.las","filename":"/artifacts/JointBuildGS/'"${task_rel}"'/prep/semantic_gt/current_eval_csf_voxel025.laz","a_srs":"EPSG:25832","minor_version":4,"dataformat_id":3,"compression":"lazperf"}' ']}' >"${pipeline}"
  run_tools pdal pipeline "/artifacts/JointBuildGS/${task_rel}/prep/semantic_gt/csf_pipeline.json" \
    >"${logs_root}/06_semantic_csf.log" 2>&1
fi
run_dev python scripts/p2/e1_e6_techdev_v1/make_semantic_gt.py \
  --artifact-root /artifacts/JointBuildGS \
  --classified-scan "/artifacts/JointBuildGS/${task_rel}/prep/semantic_gt/current_eval_csf_voxel025.laz" \
  --output-root "/artifacts/JointBuildGS/${task_rel}/prep/semantic_gt" \
  >"${logs_root}/06_semantic_gt.log" 2>&1
run_dev python scripts/p2/e1_e6_techdev_v1/make_semantic_gt_dense.py \
  --artifact-root /artifacts/JointBuildGS \
  --classified-scan "/artifacts/JointBuildGS/${task_rel}/prep/semantic_gt/current_eval_csf_voxel025.laz" \
  --output-root "/artifacts/JointBuildGS/${task_rel}/prep/semantic_gt_dense" \
  >"${logs_root}/06_semantic_gt_dense.log" 2>&1
docker run --rm --network none --shm-size 8g \
  --gpus "device=${JBGS_SEMANTIC_GPU_INDEX:-1}" \
  --user "$(id -u):$(id -g)" -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS "${dev_image}" python \
  scripts/p2/e1_e6_techdev_v1/make_semantic_rgb_sam_v2.py \
  --artifact-root /artifacts/JointBuildGS \
  --task-root "/artifacts/JointBuildGS/${task_rel}" \
  --sam-source /artifacts/JointBuildGS/results/tum_transfer/e5_s3b0/runtime/sam_vit_b/segment-anything \
  --sam-checkpoint /artifacts/JointBuildGS/results/tum_transfer/e5_s3b0/runtime/sam_vit_b/sam_vit_b_01ec64.pth \
  --device cuda >"${logs_root}/06_semantic_rgb_sam_v2.log" 2>&1
printf 'Semantic evaluation GT complete: %s\n' "${semantic_root}"
