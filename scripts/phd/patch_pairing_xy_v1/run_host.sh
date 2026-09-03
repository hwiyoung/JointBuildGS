#!/usr/bin/env bash
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
artifact_root="${JBGS_ARTIFACT_ROOT_HOST:-$(realpath "${repo_root}/../JointBuildGS-artifacts")}"
docker run --rm -v "${repo_root}:/workspace/JointBuildGS:ro" -v "${artifact_root}:/artifacts/JointBuildGS" \
  -e "JBGS_SOURCE_GIT_HEAD=$(git -C "${repo_root}" rev-parse HEAD)" -w /workspace/JointBuildGS jointbuildgs:dev \
  python scripts/phd/patch_pairing_xy_v1/run.py "${1:-run-and-validate}"
