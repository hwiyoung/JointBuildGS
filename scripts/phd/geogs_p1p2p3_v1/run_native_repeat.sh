#!/usr/bin/env bash
# One supplemental region at a time. The parent scheduler owns GPU assignment.
set -euo pipefail
region="${1:?Usage: run_native_repeat.sh P1|P2|P3 0|1}"
gpu="${2:?GPU index assigned by the parent scheduler}"
case "$region" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
if [[ -s "$task_root/contracts/extraction_resource_v3.json" ]]; then
  exec bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_native_repeat_resource_v3.sh" "$region" "$gpu"
fi
export JBGS_RUNTIME_REVISION=allocator_v2
source "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime_paths.sh"
mkdir -p "$queue_root/locks"
exec 9>"$queue_root/locks/gpu${gpu}.lock"
flock -n 9
contract="$task_root/contracts/supplemental_repeat_v1.json"
cmp -s "$contract" "$repo_root/configs/phd/geogs_p1p2p3_v1/supplemental_repeat_v1.json"
image_id=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
test "$(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}')" = "$image_id"
region_root="$task_root/native_repeat_allocator_v2/$region"
test ! -e "$region_root"
mkdir -p "$task_root/native_repeat_allocator_v2"
mkdir "$region_root"
cp "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_native_repeat.sh" "$region_root/repeat_runner_snapshot.sh"
docker run --rm --network none --cpus 2 --memory 2g --user "$(id -u):$(id -g)" \
  --env JBGS_RUNTIME_IMAGE_ID="$image_id" \
  --mount "type=bind,src=$repo_root/scripts/phd/geogs_p1p2p3_v1,dst=/audit,readonly" \
  --mount "type=bind,src=$task_root/contracts/execution_v1.json,dst=/config.json,readonly" \
  --mount "type=bind,src=$runtime_layout,dst=/runtime_layout.json,readonly" \
  --mount "type=bind,src=$contract,dst=/repeat_contract.json,readonly" \
  --mount "type=bind,src=$runs_root,dst=/primary,readonly" \
  "$image_id" python /audit/repeat_contract.py --config /config.json \
  --runtime-layout /runtime_layout.json --contract /repeat_contract.json --primary-runs /primary \
  --region "$region" > "$region_root/readiness.json" 2> "$region_root/readiness.log"
for phase in train render metrics auxiliary; do
  bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_regional_phase.sh" \
    "$region" D005_Pnative "$phase" "$gpu" "$contract"
done
