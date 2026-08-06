#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
docker run --rm --network none --shm-size 16g --gpus "device=${JBGS_GPU_INDEX:-0}" \
  --user "$(id -u):$(id -g)" -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp \
  -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS "${dev_image}" python scripts/p2/e1_e6_techdev_v1/evaluate.py \
  --artifact-root /artifacts/JointBuildGS --task-root "/artifacts/JointBuildGS/${task_rel}" \
  >"${logs_root}/07_eval.log" 2>&1
printf 'Evaluation report complete: %s/report.md\n' "${task_root}"
