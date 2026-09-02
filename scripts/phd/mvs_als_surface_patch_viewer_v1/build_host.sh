#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
artifact_root="${JBGS_ARTIFACT_ROOT_HOST:-$(realpath "${repo_root}/../JointBuildGS-artifacts")}"
command_name="${1:-build-and-validate}"

case "${command_name}" in
  build|validate|build-and-validate) ;;
  *) printf 'usage: %s [build|validate|build-and-validate]\n' "$0" >&2; exit 2 ;;
esac

docker run --rm \
  -v "${repo_root}:/workspace/JointBuildGS:ro" \
  -v "${artifact_root}:/artifacts/JointBuildGS" \
  -w /workspace/JointBuildGS \
  jointbuildgs:dev \
  python scripts/phd/mvs_als_surface_patch_viewer_v1/build.py "${command_name}"
