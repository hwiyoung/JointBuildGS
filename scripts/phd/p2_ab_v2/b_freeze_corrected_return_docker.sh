#!/usr/bin/env bash
set -euo pipefail
b_repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
b_artifacts=$(realpath "$b_repo/../JointBuildGS-artifacts")
b_output="$b_artifacts/phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-B-CORRECTED-RETURN-v1"
mkdir "$b_output"
docker run --rm --network none --entrypoint python \
 --mount "type=bind,src=$b_repo,dst=/workspace/JointBuildGS,readonly" \
 --mount "type=bind,src=$b_artifacts,dst=/artifacts/JointBuildGS,readonly" \
 --mount "type=bind,src=$b_output,dst=/output" \
 --workdir /workspace/JointBuildGS --env PYTHONDONTWRITEBYTECODE=1 \
 jointbuildgs:dev -m scripts.phd.p2_ab_v2.b_freeze_corrected_return --config configs/phd/p2_ab_v2/b_corrected_return_v1.json
