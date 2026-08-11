#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
artifact_root="${1:-${JBGS_ARTIFACT_ROOT:-$(cd "$repo_root/../JointBuildGS-artifacts" && pwd)}}"

[[ "$artifact_root" == /* && -d "$artifact_root" ]] || { echo "artifact root must be an existing absolute directory" >&2; exit 2; }
docker run --rm --network none \
  --user "$(id -u):$(id -g)" --cpus 12 --memory 96g --pids-limit 4096 \
  -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/JointBuildGS \
  -v "$repo_root:/workspace/JointBuildGS:ro" \
  -v "$artifact_root:/artifacts/JointBuildGS:rw" \
  -w /workspace/JointBuildGS jointbuildgs:dev \
  python -B scripts/p2/e1_e6_roofer_ox_review_v1/build.py \
  --artifact-root /artifacts/JointBuildGS --repo-root /workspace/JointBuildGS
