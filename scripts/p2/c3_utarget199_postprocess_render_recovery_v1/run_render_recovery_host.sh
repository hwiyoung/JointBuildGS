#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_render_recovery_host.sh ARTIFACT_ROOT PROJECT_IMAGE SOURCE_COMMIT}"
project_image="${2:?missing project image}"
source_commit="${3:?missing source commit}"
source_rel="phase-payloads/p2/c3_utarget199_postprocess_v1/P2-C3-UTARGET199-POSTPROCESS-v1"
task_rel="phase-payloads/p2/c3_utarget199_postprocess_render_recovery_v1/P2-C3-UTARGET199-POSTPROCESS-RENDER-RECOVERY-v1"
training_rel="phase-payloads/p2/c1_c2_c3_utarget199_v1/P2-C1-C2-C3-UTARGET199-C3-2-GPU0-RECOVERY-v1"
data_rel="phase-payloads/p0-audit/data/work/mvs/colmap_dense"
source_root="${artifact_root}/${source_rel}"
task_root="${artifact_root}/${task_rel}"
training_root="${artifact_root}/${training_rel}"
accepted_rel="artifacts/manifests/handoffs/P2-W2C-C3-UTARGET199-POSTPROCESS-RENDER-RECOVERY-v1/100-accepted.json"
packet_rel="docs/handoffs/P2_W2C_C3_UTARGET199_POSTPROCESS_RENDER_RECOVERY_v1.md"
expected_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"

if [[ "$(docker image inspect "${project_image}" --format '{{.Id}}')" != "${expected_image}" ]]; then
  echo "project image identity mismatch" >&2
  exit 2
fi
timeout 300 git -C "${repo_root}" fetch origin main
if [[ "$(git -C "${repo_root}" rev-parse HEAD)" != "$(git -C "${repo_root}" rev-parse origin/main)" \
  || -n "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "HEAD/origin/source/clean authority mismatch" >&2
  exit 2
fi
if [[ "$(sed -n 's/^- source_commit: `\([0-9a-f]\{40\}\)`.*$/\1/p' "${repo_root}/${packet_rel}")" != "${source_commit}" ]]; then
  echo "packet source commit mismatch" >&2
  exit 2
fi
[[ -f "${repo_root}/${accepted_rel}" ]] || { echo "accepted receipt missing" >&2; exit 2; }
[[ -d "${source_root}" && ! -L "${source_root}" ]] || { echo "preserved source namespace missing" >&2; exit 2; }
[[ ! -e "${task_root}" ]] || { echo "fresh add-once recovery namespace required" >&2; exit 2; }

docker run --rm --network none --entrypoint python \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
  -w /workspace/JointBuildGS "${project_image}" \
  scripts/repository/validate_two_host_handoff.py "${accepted_rel}" \
    --repo . --artifact-root /artifacts/JointBuildGS --origin-ref origin/main --head-ref HEAD

docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS:rw" \
  -w /workspace/JointBuildGS "${project_image}" \
  scripts/p2/c3_utarget199_postprocess_render_recovery_v1/recover_render.py recover \
    --source-root "/artifacts/JointBuildGS/${source_rel}" \
    --output-root "/artifacts/JointBuildGS/${task_rel}"

mkdir -p "${task_root}/control/torch_extensions" "${task_root}/control/cache"
if [[ -f "${source_root}/control/torch_extensions/gsplat_cuda/gsplat_cuda.so" ]]; then
  cp -a "${source_root}/control/torch_extensions/." "${task_root}/control/torch_extensions/"
fi

gpu_index=""
while IFS=, read -r index free; do
  index="${index// /}"
  free="${free// /}"
  if (( free >= 18000 )); then
    gpu_index="${index}"
    break
  fi
done < <(nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits)
[[ -n "${gpu_index}" ]] || { echo "no GPU satisfies 18 GiB render guard" >&2; exit 2; }

render_condition() {
  local condition_id="$1"
  local checkpoint_rel="$2"
  docker run --rm --network none --shm-size 8g --gpus "device=${gpu_index}" \
    --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
    -e CUDA_VISIBLE_DEVICES=0 -e HOME=/tmp \
    -e XDG_CACHE_HOME=/task/control/cache \
    -e TORCH_EXTENSIONS_DIR=/task/control/torch_extensions \
    -v "${repo_root}:/workspace/JointBuildGS:ro" \
    -v "${task_root}:/task:rw" \
    -v "${training_root}/${checkpoint_rel}:/checkpoint/final.pt:ro" \
    -v "${artifact_root}/${data_rel}:/render_inputs/${data_rel}:ro" \
    -w /workspace/JointBuildGS "${project_image}" \
    python scripts/p2/c3_utarget199_postprocess_v1/render_gs.py condition \
      --output-root /task --artifact-root /render_inputs --checkpoint /checkpoint/final.pt \
      --condition-id "${condition_id}" --device cuda
}

render_condition C3_1_SEM c3/c3_1_sem/seed0/ckpt/final.pt
render_condition C3_2_SEM_DEPTH c3/c3_2_sem_depth/seed0/ckpt/final.pt
docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" --cpus 2 --memory 8g \
  -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${task_root}:/task:rw" \
  -w /workspace/JointBuildGS "${project_image}" \
  scripts/p2/c3_utarget199_postprocess_v1/render_gs.py finalize --output-root /task

docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${task_root}:/task:rw" \
  -v "${training_root}:/training:ro" -w /workspace/JointBuildGS "${project_image}" \
  scripts/p2/c3_utarget199_postprocess_v1/render_case_sheets.py \
    --task-root /task --checkpoint-root /training

docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" --cpus 2 --memory 8g \
  -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${task_root}:/task:rw" \
  -w /workspace/JointBuildGS "${project_image}" \
  scripts/p2/c3_utarget199_postprocess_render_recovery_v1/recover_render.py complete \
    --output-root /task

echo "C3 U_target=199 render recovery complete: ${task_root}"
