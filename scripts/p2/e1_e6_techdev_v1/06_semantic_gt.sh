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
printf 'Semantic evaluation GT complete: %s\n' "${semantic_root}"
