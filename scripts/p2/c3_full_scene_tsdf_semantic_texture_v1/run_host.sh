#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
relative_root="phase-payloads/p2/c3_full_scene_tsdf_semantic_texture_v1/P2-C3-FULL-SCENE-TSDF-SEMANTIC-TEXTURE-v1"
final_root="${artifact_root}/${relative_root}"
partial_root="${final_root}.partial"
image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"
gpu_index="${JBGS_C3_FULL_TSDF_GPU_INDEX:-1}"

[[ -z "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]] || { echo "clean source required" >&2; exit 2; }
[[ "$(git -C "${repo_root}" rev-parse HEAD)" == "$(git -C "${repo_root}" rev-parse origin/main)" ]] || { echo "HEAD must equal origin/main" >&2; exit 2; }
[[ "$(docker image inspect "${image}" --format '{{.Id}}')" == "${image}" ]] || { echo "project image mismatch" >&2; exit 2; }
[[ ! -e "${final_root}" && ! -e "${partial_root}" ]] || { echo "add-once namespace exists" >&2; exit 2; }
source_commit="$(git -C "${repo_root}" rev-parse HEAD)"

docker run --rm --network none -v "${artifact_root}:/artifacts/JointBuildGS:rw" "${image}" \
  sh -lc "install -d -o $(id -u) -g $(id -g) -m 0755 '/artifacts/JointBuildGS/${relative_root}.partial'"
docker run --rm --network none --gpus "device=${gpu_index}" --shm-size 8g --cpus 8 --memory 64g --pids-limit 2048 \
  --user "$(id -u):$(id -g)" -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e PYTHONDONTWRITEBYTECODE=1 \
  -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS:rw" \
  -w /workspace/JointBuildGS "${image}" python -B -m scripts.p2.c3_full_scene_tsdf_semantic_texture_v1.run \
  --output-root "/artifacts/JointBuildGS/${relative_root}.partial" --artifact-root /artifacts/JointBuildGS \
  --repo-root /workspace/JointBuildGS --source-commit "${source_commit}" --device cuda
docker run --rm --network none -v "${artifact_root}:/artifacts/JointBuildGS:rw" "${image}" \
  sh -lc "mv -- '/artifacts/JointBuildGS/${relative_root}.partial' '/artifacts/JointBuildGS/${relative_root}'"
echo "completed: ${final_root}"
