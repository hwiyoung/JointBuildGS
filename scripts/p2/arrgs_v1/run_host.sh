#!/usr/bin/env bash
# ARRGS host runner: GPU container with repo + artifacts mounts and a warm
# torch-extensions cache (gsplat JIT).
# Usage: run_host.sh <gpu-id> <python-args...>
set -euo pipefail
GPU="$1"; shift
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
ART="$(cd "$REPO/../JointBuildGS-artifacts" && pwd)"
CACHE="$ART/phase-payloads/p2/arrgs_v1/cache/torch_extensions"
mkdir -p "$CACHE"
exec docker run --rm --network none --gpus "\"device=$GPU\"" \
  --shm-size 8g \
  --user "$(id -u):$(id -g)" -e HOME=/tmp -e OPENCV_IO_ENABLE_OPENEXR=1 \
  -v "$REPO":/workspace/JointBuildGS \
  -v "$ART":/artifacts/JointBuildGS \
  -e JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS \
  -e TORCH_EXTENSIONS_DIR=/artifacts/JointBuildGS/phase-payloads/p2/arrgs_v1/cache/torch_extensions \
  -e PYTHONPATH=/workspace/JointBuildGS/scripts/p2/arrgs_v1 \
  -w /workspace/JointBuildGS \
  jointbuildgs:dev python -u "$@"
