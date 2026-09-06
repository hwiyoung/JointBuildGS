#!/usr/bin/env bash
set -euo pipefail
c_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
c_artifacts=$(realpath "$c_repo/../JointBuildGS-artifacts")
c_output="$c_artifacts/phase-payloads/phd/p2_ab_v6/PHD-P2-AB-V6-C-REFERENCE-v1"
mkdir "$c_output"
docker run --rm --network none --cpus 6 --memory 20g --entrypoint python \
  --mount "type=bind,src=$c_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$c_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$c_output,dst=/output" --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 --env OMP_NUM_THREADS=2 jointbuildgs:dev \
  -m scripts.phd.p2_ab_v6.c_reference_evaluate \
  --b-root /artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v6/PHD-P2-AB-V6-B-SURFACE-v3 \
  --output /output/evaluation 2>&1 | tee "$c_output/console.log"
