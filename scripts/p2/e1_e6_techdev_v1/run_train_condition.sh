#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

condition="${1:?condition E3-E6 required}"
gpu_index="${2:-0}"
case "${condition}" in
  E3) run_name="E3_GS_IMAGE" ;;
  E4) run_name="E4_GS_ALS_UNWEIGHTED" ;;
  E5) run_name="E5_GS_ALS_WB" ;;
  E6) run_name="E6_GS_LOD2_PLANES_DIAGNOSTIC" ;;
  *) echo "unknown condition: ${condition}" >&2; exit 2 ;;
esac
run_root="${task_root}/runs/${run_name}"
runtime_config="${prep_root}/runtime_configs/${condition}.yaml"
final_checkpoint="${run_root}/ckpt/final.pt"
if [[ -f "${final_checkpoint}" ]]; then
  printf 'SKIP %s: final checkpoint exists\n' "${condition}"
  exit 0
fi
if [[ -n "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "training requires a clean source checkout" >&2
  exit 2
fi
mkdir -p "${run_root}/control" "${prep_root}/runtime_configs"
run_dev python scripts/p2/e1_e6_techdev_v1/materialize_config.py "${condition}" \
  --repository-root /workspace/JointBuildGS --artifact-root /artifacts/JointBuildGS \
  --output "/artifacts/JointBuildGS/${task_rel}/prep/runtime_configs/${condition}.yaml" \
  >"${logs_root}/02_materialize_${condition}.log" 2>&1
nvidia-smi -q -i "${gpu_index}" >"${run_root}/control/gpu_before.txt"
start_epoch="$(date +%s)"
vram_log="${run_root}/control/vram_used_mib.tsv"
: >"${vram_log}"
docker run --rm --network none --shm-size 16g \
  --gpus "device=${gpu_index}" \
  --user "$(id -u):$(id -g)" \
  -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp \
  -e XDG_CACHE_HOME="/artifacts/JointBuildGS/${task_rel}/control/cache" \
  -e TORCH_EXTENSIONS_DIR="/artifacts/JointBuildGS/${task_rel}/control/torch_extensions" \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS "${dev_image}" \
  python -m src.stage2.train --config "/artifacts/JointBuildGS/${task_rel}/prep/runtime_configs/${condition}.yaml" \
  >"${logs_root}/02_train_${condition}.log" 2>&1 &
training_pid="$!"
while kill -0 "${training_pid}" 2>/dev/null; do
  printf '%s\t' "$(date +%s)" >>"${vram_log}"
  nvidia-smi --id="${gpu_index}" --query-gpu=memory.used --format=csv,noheader,nounits \
    >>"${vram_log}" 2>/dev/null || printf '0\n' >>"${vram_log}"
  sleep 2
done
set +e
wait "${training_pid}"
training_status="$?"
set -e
end_epoch="$(date +%s)"
nvidia-smi -q -i "${gpu_index}" >"${run_root}/control/gpu_after.txt"
max_vram_mib="$(awk 'BEGIN{m=0} $2+0>m{m=$2+0} END{print m}' "${vram_log}")"
printf '{"condition":"%s","wall_seconds":%d,"gpu_index":%d,"max_vram_mib":%d,"exit_code":%d,"scientific_verdict":null}\n' \
  "${condition}" "$((end_epoch-start_epoch))" "${gpu_index}" "${max_vram_mib}" "${training_status}" \
  >"${run_root}/control/operation.json"
if [[ "${training_status}" -ne 0 ]]; then
  tail -n 20 "${logs_root}/02_train_${condition}.log" >&2
  exit "${training_status}"
fi
test -f "${final_checkpoint}"
printf '%s training complete: %s\n' "${condition}" "${final_checkpoint}"
