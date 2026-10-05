#!/usr/bin/env bash
set -euo pipefail
region="${1:?P1 P2 P3}"
gpu="${2:?0 or1}"
case "$region" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
export JBGS_RUNTIME_REVISION=allocator_v2
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
exec 9>"$task_root/queue_allocator_v2/locks/gpu${gpu}.lock"
flock -n 9
mkdir -p "$task_root/queue_allocator_v2/resource_v3/repeat_attempts/$region"
attempt="$(mktemp -d "$task_root/queue_allocator_v2/resource_v3/repeat_attempts/$region/attempt.XXXXXX")"
cp -p -- "${BASH_SOURCE[0]}" "$attempt/runner_snapshot.sh"
exec > >(exec tee -a "$attempt/run.log" 9>&-) 2>&1
check() {
  docker run --rm --network none --cpus 2 --memory 4g --user "$(id -u):$(id -g)" --env PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,src=$task_root,dst=/task,readonly" \
    --mount "type=bind,src=$repo_root/scripts/phd/geogs_p1p2p3_v1,dst=/audit,readonly" \
    --mount "type=bind,src=$attempt,dst=/operational" "$image" \
    python /audit/runtime/resource_phase_integrity.py "$@"
}
check --mode primary_ready --output /operational/primary_readiness.json
for phase in train render metrics auxiliary; do
  action="$(check --mode phase --region "$region" --condition D005_Pnative --phase "$phase" --run-family native_repeat_1)"
  if [[ "$action" == SKIP ]]; then continue; fi
  test "$action" = RUN
  if [[ "$phase" == train ]]; then
    while [[ "$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)" -lt 25165824 ]]; do sleep 5; done
  elif [[ "$phase" == render ]]; then
    while [[ "$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)" -lt 41943040 ]]; do sleep 5; done
  fi
  if [[ "$phase" == auxiliary ]]; then
    bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_auxiliary_resource_v3.sh" "$region" D005_Pnative "$gpu" native_repeat_1
  else
    bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_regional_phase.sh" "$region" D005_Pnative "$phase" "$gpu" \
      "$task_root/contracts/supplemental_repeat_v1.json"
  fi
done
check --mode job_complete --region "$region" --condition D005_Pnative --run-family native_repeat_1 --output /operational/complete.json
