#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
artifact_root="${JBGS_ARTIFACT_ROOT_HOST:-$(realpath "${repo_root}/../JointBuildGS-artifacts")}"
source_git_head="$(git -C "${repo_root}" rev-parse HEAD)"
command_name="${1:-run-and-validate}"

docker run --rm \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -e "JBGS_SOURCE_GIT_HEAD=${source_git_head}" \
  -w /workspace/JointBuildGS \
  jointbuildgs:dev \
  python scripts/phd/region_unit_v1/run.py "${command_name}"
