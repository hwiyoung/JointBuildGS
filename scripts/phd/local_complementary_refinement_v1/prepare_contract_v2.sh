#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
parent=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
exec docker run --rm --name jbgs-lc-v2-contract --network none --cpus 2 --memory 2g \
    --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1,dst=/audit,readonly" \
    --mount "type=bind,src=$task_root/contracts/main_v2/experiment_v2.json,dst=/config.json,readonly" \
    --mount "type=bind,src=$task_root/contracts/main_v2,dst=/contracts" \
    --mount "type=bind,src=$task_root/contracts,dst=/preparation,readonly" \
    --mount "type=bind,src=$task_root/preflight/input_audit_v2,dst=/input_audit,readonly" \
    --mount "type=bind,src=$task_root/source_v2/local_source_provenance.json,dst=/parent_source_identity.json,readonly" \
    --mount "type=bind,src=$parent/inputs,dst=/parent_inputs,readonly" \
    --mount "type=bind,src=$parent/runs_allocator_v2,dst=/parent_runs,readonly" \
    --mount "type=bind,src=$parent/runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000,dst=/anchors/P1,readonly" \
    --mount "type=bind,src=$parent/runs_allocator_v2/P2/D005_Pnative/model/jbgs_complete/iteration_8000,dst=/anchors/P2,readonly" \
    --mount "type=bind,src=$parent/runs_allocator_v2/P3/D005_Pnative/model/jbgs_complete/iteration_8000,dst=/anchors/P3,readonly" \
    sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
    python /audit/prepare_contract_v2.py
