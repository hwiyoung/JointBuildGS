#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:?usage: run_host.sh ARTIFACT_ROOT PROJECT_IMAGE SOURCE_COMMIT RUN_ID}"
project_image="${2:?missing project image}"
source_commit="${3:?missing source commit}"
run_id="${4:?missing run ID}"
task_rel="phase-payloads/p2/selected10_c1_c4_presentation_v1/P2-SELECTED10-C1-C4-PRESENTATION-v1"
task_root="${artifact_root}/${task_rel}"
expected_image="sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774"

[[ "$(docker image inspect "${project_image}" --format '{{.Id}}')" == "${expected_image}" ]] || { echo "project image identity mismatch" >&2; exit 2; }
[[ "$(git -C "${repo_root}" rev-parse HEAD)" == "${source_commit}" ]] || { echo "HEAD/source mismatch" >&2; exit 2; }
[[ -z "$(git -C "${repo_root}" status --porcelain=v1 --untracked-files=all)" ]] || { echo "clean committed worktree required" >&2; exit 2; }
[[ ! -e "${task_root}" ]] || { echo "fresh add-once selected10 namespace required" >&2; exit 2; }
mkdir -p "${task_root}"

docker run --rm --network none --entrypoint python \
  --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --pids-limit 2048 \
  -e PYTHONDONTWRITEBYTECODE=1 -e MPLCONFIGDIR=/tmp/jbgs-mpl-cache \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS:ro" \
  -v "${task_root}:/task:rw" \
  -w /workspace/JointBuildGS "${project_image}" \
  scripts/p2/selected10_c1_c4_presentation_v1/render.py \
    --output-root /task --artifact-root /artifacts/JointBuildGS \
    --source-commit "${source_commit}" --run-id "${run_id}"

echo "selected10 C1-C4 presentation complete: ${task_root}"
