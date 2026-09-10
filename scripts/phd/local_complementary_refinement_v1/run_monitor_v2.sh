#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
exec docker run --rm --network none --cpus 1 --memory 256m -e PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1,dst=/audit,readonly" \
    --mount "type=bind,src=$task_root/main_v2/runs,dst=/runs,readonly" \
    --mount "type=bind,src=$task_root/contracts/main_v2/experiment_v2.json,dst=/config.json,readonly" \
    sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e python /audit/monitor_v2.py
