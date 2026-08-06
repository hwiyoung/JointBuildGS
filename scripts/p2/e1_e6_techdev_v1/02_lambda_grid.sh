#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

grid_root="${task_root}/lambda_grid"
mkdir -p "${grid_root}" "${prep_root}/runtime_configs/lambda_grid"
for value in 0.2 0.5 1.0; do
  key="${value/./p}"
  run_root="${grid_root}/${key}"
  final="${run_root}/ckpt/final.pt"
  if [[ -f "${final}" ]]; then
    printf 'SKIP lambda %s\n' "${value}"
    continue
  fi
  config="${prep_root}/runtime_configs/lambda_grid/${key}.yaml"
  run_dev python scripts/p2/e1_e6_techdev_v1/materialize_config.py E5 \
    --repository-root /workspace/JointBuildGS --artifact-root /artifacts/JointBuildGS \
    --max-iter 7000 --als-depth-weight "${value}" \
    --out-dir "/artifacts/JointBuildGS/${task_rel}/lambda_grid/${key}" \
    --output "/artifacts/JointBuildGS/${task_rel}/prep/runtime_configs/lambda_grid/${key}.yaml" \
    >"${logs_root}/02_lambda_${key}_materialize.log" 2>&1
  docker run --rm --network none --shm-size 16g --gpus "device=${JBGS_GPU_INDEX:-0}" \
    --user "$(id -u):$(id -g)" -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp \
    -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS" \
    -w /workspace/JointBuildGS "${dev_image}" python -m src.stage2.train \
    --config "/artifacts/JointBuildGS/${task_rel}/prep/runtime_configs/lambda_grid/${key}.yaml" \
    >"${logs_root}/02_lambda_${key}.log" 2>&1
done
run_dev python scripts/p2/e1_e6_techdev_v1/select_lambda.py \
  --grid-root "/artifacts/JointBuildGS/${task_rel}/lambda_grid" \
  --prep-root "/artifacts/JointBuildGS/${task_rel}/prep" \
  >"${logs_root}/02_lambda_select.log" 2>&1
printf 'Lambda grid complete: %s\n' "${prep_root}/lambda_grid.md"
