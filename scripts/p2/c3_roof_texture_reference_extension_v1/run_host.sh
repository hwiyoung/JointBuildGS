#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${JBGS_ARTIFACT_ROOT:-/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts}"
relative_root="phase-payloads/p2/c3_roof_texture_reference_extension_v1/P2-C3-ROOF-TEXTURE-C1-LOD2-REFERENCE-EXTENSION-v4"
output_root="${artifact_root}/${relative_root}"
image="jointbuildgs:dev"; expected_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"; host_uid="$(id -u)"; host_gid="$(id -g)"
[[ -z "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]] || { echo "clean source required" >&2; exit 2; }
[[ "$(git -C "${repo_root}" rev-parse HEAD)" == "$(git -C "${repo_root}" rev-parse origin/main)" ]] || { echo "HEAD must equal origin/main" >&2; exit 2; }
[[ "$(docker image inspect "${image}" --format '{{.Id}}')" == "${expected_image}" ]] || { echo "project image mismatch" >&2; exit 2; }
[[ ! -e "${output_root}" ]] || { echo "add-once output exists: ${output_root}" >&2; exit 2; }
source_commit="$(git -C "${repo_root}" rev-parse HEAD)"
docker run --rm --network none -v "${artifact_root}:/artifacts/JointBuildGS" "${image}" sh -lc "install -d -o ${host_uid} -g ${host_gid} -m 0755 '/artifacts/JointBuildGS/${relative_root}'"
docker run --rm --network none --user "${host_uid}:${host_gid}" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS" -w /workspace/JointBuildGS "${image}" python -B -m scripts.p2.c3_roof_texture_reference_extension_v1.compose --output-root "/artifacts/JointBuildGS/${relative_root}" --artifact-root /artifacts/JointBuildGS --source-commit "${source_commit}"
