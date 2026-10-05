#!/usr/bin/env bash
# Narrow recovery of the two successful P1 trains followed by launcher EOF.
set -euo pipefail
condition="${1:?D005_Pnative or D0005_Pnative}"
gpu="${2:?GPU 0 or 1}"
case "$condition:$gpu" in D005_Pnative:0|D0005_Pnative:1) ;; *) exit 2 ;; esac
test "${JBGS_RUNTIME_REVISION:-allocator_v2}" = allocator_v2
export JBGS_RUNTIME_REVISION=allocator_v2
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
queue="$task_root/queue_allocator_v2"
job="P1_$condition"
run_path="$task_root/runs_allocator_v2/P1/$condition"
image=jointbuildgs:geogs-official-db40c95-compat-v1
test "$(docker image inspect "$image" --format '{{.Id}}')" = sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
exec 9>"$queue/locks/gpu${gpu}.lock"
flock -n 9
test -s "$queue/failed/$job"
test ! -e "$queue/done/$job"
test -s "$queue/claims/$job/run.log"
test -s "$task_root/runtime/launcher_recovery_v1/run_regional_phase_before_exec.sh"
mkdir -p "$queue/recovery"
attempt="$(mktemp -d "$queue/recovery/${job}.XXXXXX")"
cp -p -- "$queue/failed/$job" "$attempt/original_failed_marker"
cp -p -- "$queue/claims/$job/run.log" "$attempt/original_claim_run.log"
cp -p -- "${BASH_SOURCE[0]}" "$attempt/recovery_launcher_snapshot.sh"
cp -p -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_regional_phase.sh" "$attempt/phase_launcher_snapshot.sh"
cp -p -- "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime/verify_completed_train_recovery.py" "$attempt/verifier_snapshot.py"
printf '%s\n' "Recovery evidence: $attempt"
exec > >(tee -a "$attempt/recovery.log") 2>&1
verify() {
  docker run --rm --network none --cpus 2 --memory 2g --user "$(id -u):$(id -g)" \
    --mount "type=bind,src=$attempt,dst=/recovery" \
    --mount "type=bind,src=$run_path,dst=/run,readonly" \
    --mount "type=bind,src=$task_root/contracts/execution_v1.json,dst=/config.json,readonly" \
    --mount "type=bind,src=$task_root/contracts/runtime_layout_allocator_v2.json,dst=/runtime_layout.json,readonly" \
    --mount "type=bind,src=$task_root/inputs/P1/input_manifest.json,dst=/input_manifest.json,readonly" \
    --mount "type=bind,src=$task_root/sources/GeoGS-state-camera-v1,dst=/source,readonly" \
    --mount "type=bind,src=$task_root/runtime/launcher_recovery_v1,dst=/launcher_archive,readonly" \
    "$image" python /recovery/verifier_snapshot.py --condition "$condition" --mode "$1"
}
verify preflight
for phase in render metrics auxiliary; do
  if [[ -e "$run_path/${phase}_receipt.json" ]]; then
    printf '%s\n' "Previously validated PASS phase retained: $phase"
    continue
  fi
  cmp -s "$attempt/phase_launcher_snapshot.sh" "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_regional_phase.sh"
  bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_regional_phase.sh" P1 "$condition" "$phase" "$gpu"
done
verify complete
cmp -s "$queue/failed/$job" "$attempt/original_failed_marker"
cmp -s "$queue/claims/$job/run.log" "$attempt/original_claim_run.log"
test ! -e "$attempt/archived_failed_marker"
mv -n -- "$queue/failed/$job" "$attempt/archived_failed_marker"
test ! -e "$queue/failed/$job"
(set -o noclobber; printf '%s\n' "$attempt/complete.json" > "$queue/done/$job")
printf '%s\n' "$job recovered; all four phases verified; original failure and log retained."
