#!/usr/bin/env bash
set -euo pipefail
region="${1:?P1 P2 P3}"
gpu="${2:?0 or 1}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
source "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime_paths.sh"
mkdir -p "$parity_root/$region"
exec 8>"$parity_root/$region/anchor.lock"
flock 8
gate="$parity_root/$region/anchor_gate.json"
if [[ -s "$gate" ]]; then exit 0; fi
if [[ ! -s "$parity_root/$region/restore_probe/one_step_probe.json" ]]; then
  test ! -e "$parity_root/$region/restore_probe"
  bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_regional_probe.sh" "$region" "$gpu"
fi
if [[ ! -s "$parity_root/$region/restart/parity_receipt.json" ]]; then
  bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_regional_phase.sh" "$region" D005_Pnative parity "$gpu"
fi
set +e
docker run --rm --network none --cpus 4 --memory 24g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$repo_root/scripts/phd/geogs_p1p2p3_v1,dst=/audit,readonly" \
  --mount "type=bind,src=$baseline_root/model/jbgs_complete/iteration_8100,dst=/native,readonly" \
  --mount "type=bind,src=$parity_root/$region,dst=/parity" \
  jointbuildgs:geogs-official-db40c95-compat-v1 python /audit/compare_states.py \
  --left /native/checkpoint.pth --right /parity/restart/model/jbgs_complete/iteration_8100/checkpoint.pth \
  --output /parity/continuation_comparison.json
compare_code=$?
set -e
if [[ "$compare_code" != 0 && "$compare_code" != 2 ]]; then exit "$compare_code"; fi
docker run --rm --network none --cpus 2 --memory 2g --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$repo_root/scripts/phd/geogs_p1p2p3_v1,dst=/audit,readonly" \
  --mount "type=bind,src=$parity_root/$region,dst=/parity" \
  --mount "type=bind,src=$anchor_root/receipt.json,dst=/anchor_receipt.json,readonly" \
  "${runtime_mounts[@]}" \
  jointbuildgs:geogs-official-db40c95-compat-v1 python /audit/seal_anchor_gate.py --region "$region"
