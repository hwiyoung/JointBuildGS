#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: build_web_host.sh ARTIFACT_ROOT}"
tools_image="jointbuildgs-p0-tools:t0"
expected_tools_id="sha256:02b4b7bb2e35e9b88bcc8457678ed8f178cca8f76f22b1b62f02721359e46be8"
[[ "${artifact_root}" == /* && -d "${artifact_root}" ]] || { echo "artifact root must be an existing absolute directory" >&2; exit 2; }
[[ "$(docker image inspect "${tools_image}" --format '{{.Id}}')" == "${expected_tools_id}" ]] || { echo "tools image identity mismatch" >&2; exit 2; }

docker run --rm --network none --entrypoint /bin/sh \
  --user "$(id -u):$(id -g)" --cpus 12 --memory 64g --pids-limit 4096 \
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS:rw" \
  -w /workspace/JointBuildGS "${tools_image}" -lc \
  "python -B -m scripts.p2.c2_c3_rendered_depth_shared_footprint_199_v1.build_web --artifact-root /artifacts/JointBuildGS --repo-root /workspace/JointBuildGS"
