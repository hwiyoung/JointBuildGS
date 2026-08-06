#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

for condition in E3 E4 E5 E6; do
  case "${condition}" in
    E3) run_name=E3_GS_IMAGE ;;
    E4) run_name=E4_GS_ALS_UNWEIGHTED ;;
    E5) run_name=E5_GS_ALS_WB ;;
    E6) run_name=E6_GS_LOD2_PLANES_DIAGNOSTIC ;;
  esac
  run_root="${task_root}/runs/${run_name}"
  receipt="${run_root}/pointcloud/extraction_receipt.json"
  if [[ -f "${receipt}" ]]; then printf 'SKIP extraction %s\n' "${condition}"; continue; fi
  test -f "${run_root}/ckpt/final.pt"
  docker run --rm --network none --shm-size 16g --gpus "device=${JBGS_GPU_INDEX:-0}" \
    --user "$(id -u):$(id -g)" -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp \
    -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS" \
    -w /workspace/JointBuildGS "${dev_image}" python \
    scripts/p2/e1_e6_techdev_v1/extract_tsdf.py \
    --checkpoint "/artifacts/JointBuildGS/${task_rel}/runs/${run_name}/ckpt/final.pt" \
    --data-root /artifacts/JointBuildGS/phase-payloads/p0-audit/data/work/mvs/colmap_dense \
    --view-roles "/artifacts/JointBuildGS/${task_rel}/prep/view_roles.json" \
    --output-root "/artifacts/JointBuildGS/${task_rel}/runs/${run_name}" \
    --condition "${condition}" >"${logs_root}/03_extract_${condition}.log" 2>&1
done
printf 'E3-E6 TSDF extraction complete.\n'
