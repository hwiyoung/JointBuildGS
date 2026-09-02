#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
artifact_root="$(realpath "${repo_root}/../JointBuildGS-artifacts")"
source_git_head="$(git -C "${repo_root}" rev-parse HEAD)"

docker run --rm \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -e "JBGS_SOURCE_GIT_HEAD=${source_git_head}" \
  -e "JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS \
  jointbuildgs:dev \
  python scripts/phd/mvs_als_current_view_render_v1/render.py run-and-validate
