#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
mkdir -p "$task_root/contracts"
contract="$task_root/contracts/execution_v1.json"
if [[ -e "$contract" ]]; then
  cmp "$repo_root/configs/phd/geogs_p1p2p3_v1/experiment_v1.json" "$contract"
else
  cp --no-clobber "$repo_root/configs/phd/geogs_p1p2p3_v1/experiment_v1.json" "$contract"
fi
for region in P1 P2 P3; do
  docker run --rm --network none --cpus 4 --memory 8g \
    --user "$(id -u):$(id -g)" --env OPENBLAS_NUM_THREADS=4 --env OMP_NUM_THREADS=4 \
    --mount "type=bind,src=$repo_root/scripts/phd/geogs_p1p2p3_v1,dst=/audit,readonly" \
    --mount "type=bind,src=$contract,dst=/config.json,readonly" \
    --mount "type=bind,src=$task_root/runtime/da3/depth_validity_audit_v1/summary.json,dst=/depth_validity_audit.json,readonly" \
    --mount "type=bind,src=$task_root/inputs/$region,dst=/input" \
    jointbuildgs:geogs-official-db40c95-compat-v1 \
    python /audit/seal_inputs.py --config /config.json --region "$region" \
      --input /input --split /input/scene/split_manifest_da3_v2.json
done
