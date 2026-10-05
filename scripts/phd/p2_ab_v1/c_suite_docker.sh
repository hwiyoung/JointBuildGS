#!/usr/bin/env bash
set -euo pipefail
suite_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
suite_parent=$(realpath "$suite_repo/../JointBuildGS-artifacts/phase-payloads/phd/p2_ab_v1")
docker run --rm --network none --cpus 4 --memory 6g \
  --user "$(id -u):$(id -g)" --entrypoint python \
  --mount "type=bind,src=$suite_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$suite_parent,dst=/results" \
  --workdir /workspace/JointBuildGS --env PYTHONDONTWRITEBYTECODE=1 \
  --env OPENBLAS_NUM_THREADS=1 --env OMP_NUM_THREADS=1 --env MPLCONFIGDIR=/tmp/mpl \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  -m scripts.phd.p2_ab_v1.c_suite --base /results \
  --config configs/phd/p2_ab_v1/c_suite_v2.json \
  2>&1 | tee "$suite_parent/PHD-P2-AB-C-SUITE-v2.console.log"
