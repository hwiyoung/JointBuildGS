#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts/phase-payloads/phd/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1")
docker run --rm --memory 2g --cpus 2 --user "$(id -u):$(id -g)" -v "$OUT:/out" \
  --entrypoint python jointbuildgs:dev -m pip install --no-cache-dir --no-deps \
  --target /out/cache/python --report /out/cache/dependency_install.json numba==0.61.2 llvmlite==0.44.0
