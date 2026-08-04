#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
relative_root="phase-payloads/p2/c3_tsdf_roof_diagnostic_v1/P2-C3-TSDF-ROOF-DIAGNOSTIC-v1"
output_root="${artifact_root}/${relative_root}"
image="jointbuildgs:dev"
expected_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
gpu_index="${JBGS_C3_TSDF_GPU_INDEX:-1}"

if [[ -n "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "C3 TSDF diagnostic requires a clean source checkout" >&2
  exit 2
fi
head_commit="$(git -C "${repo_root}" rev-parse HEAD)"
if [[ "${head_commit}" != "$(git -C "${repo_root}" rev-parse origin/main)" ]]; then
  echo "C3 TSDF diagnostic requires HEAD=origin/main" >&2
  exit 2
fi
if [[ "$(docker image inspect "${image}" --format '{{.Id}}')" != "${expected_image}" ]]; then
  echo "project image identity mismatch" >&2
  exit 2
fi
if [[ -e "${output_root}" ]]; then
  echo "add-once output namespace already exists: ${output_root}" >&2
  exit 2
fi
free_mib="$(nvidia-smi --id="${gpu_index}" --query-gpu=memory.free --format=csv,noheader,nounits | tr -d ' ')"
if (( free_mib < 12000 )); then
  echo "GPU ${gpu_index} has less than 12000 MiB free: ${free_mib}" >&2
  exit 2
fi

docker run --rm --network none --shm-size 16g \
  --name jbgs-c3-tsdf-roof-diagnostic-v1 \
  --gpus "device=${gpu_index}" \
  --user "$(id -u):$(id -g)" \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e HOME=/tmp \
  -e XDG_CACHE_HOME=/tmp/xdg-cache \
  -e TORCH_EXTENSIONS_DIR=/tmp/torch-extensions \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "${image}" python -B -m scripts.p2.c3_tsdf_roof_diagnostic_v1.extract \
    --output-root "/artifacts/JointBuildGS/${relative_root}" \
    --artifact-root /artifacts/JointBuildGS \
    --repo-root /workspace/JointBuildGS \
    --device cuda \
    --source-commit "${head_commit}"

docker run --rm --network none --shm-size 8g \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "${image}" python -B -m scripts.p2.c3_tsdf_roof_diagnostic_v1.diagnose \
    --output-root "/artifacts/JointBuildGS/${relative_root}" \
    --artifact-root /artifacts/JointBuildGS \
    --repo-root /workspace/JointBuildGS

docker run --rm --network none --shm-size 8g \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e MPLCONFIGDIR=/tmp/matplotlib \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "${image}" python -B -m scripts.p2.c3_tsdf_roof_diagnostic_v1.render \
    --output-root "/artifacts/JointBuildGS/${relative_root}" \
    --artifact-root /artifacts/JointBuildGS

echo "C3 TSDF roof diagnostic extraction complete: ${output_root}"
