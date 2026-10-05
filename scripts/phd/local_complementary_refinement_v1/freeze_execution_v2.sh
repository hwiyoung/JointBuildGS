#!/usr/bin/env bash
set -euo pipefail
action=${1:---freeze}
[[ $action == --freeze || $action == --verify ]]
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
contracts="$task_root/contracts/main_v2"
if [[ $action == --freeze ]]; then
    [[ ! -e $contracts/execution_ready.json ]]
    for protection in native release; do
        cp -n "$task_root/main_v2/preflight/P2_LC_D005_P${protection}/probe_receipt.json" "$contracts/probe_${protection}_receipt.json"
    done
fi
exec docker run --rm --network none --cpus 1 --memory 1g --user "$(id -u):$(id -g)" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,src=$repo/scripts/phd/local_complementary_refinement_v1,dst=/audit,readonly" \
    --mount "type=bind,src=$task_root/source_v2,dst=/source,readonly" \
    --mount "type=bind,src=$task_root/main_v2/preflight,dst=/probes,readonly" \
    --mount "type=bind,src=$contracts,dst=/contracts" \
    sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
    python /audit/execution_gate_v2.py "$action" --contracts /contracts --source /source --scripts /audit --probes /probes
