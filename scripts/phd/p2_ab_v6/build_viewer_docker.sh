#!/usr/bin/env bash
set -euo pipefail
v_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
v_artifacts=$(realpath "$v_repo/../JointBuildGS-artifacts")
v_output="$v_artifacts/phase-payloads/phd/p2_ab_v6/PHD-P2-AB-V6-VIEWER-v1"
mkdir "$v_output"
docker run --rm --network none --cpus 2 --memory 4g --entrypoint python \
  --mount "type=bind,src=$v_repo,dst=/workspace/JointBuildGS,readonly" \
  --mount "type=bind,src=$v_artifacts,dst=/artifacts/JointBuildGS,readonly" \
  --mount "type=bind,src=$v_output,dst=/output" --workdir /workspace/JointBuildGS \
  --env PYTHONDONTWRITEBYTECODE=1 jointbuildgs:dev -m scripts.phd.p2_ab_v6.build_viewer \
  --b-root /artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v6/PHD-P2-AB-V6-B-SURFACE-v3 \
  --evaluation /artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v6/PHD-P2-AB-V6-C-REFERENCE-v1/evaluation/evaluation.json \
  --output /output/viewer 2>&1 | tee "$v_output/console.log"
