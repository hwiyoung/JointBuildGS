#!/usr/bin/env bash
# Operational sequencing only; scientific execution remains in isolated Docker.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
scripts="$repo_root/scripts/phd/geogs_p1p2p3_v1"
queue="$task_root/queue_allocator_v2"
exec 5>"$queue/locks/resource_v3_continuation.lock"
flock -n 5
mkdir -p "$task_root/runtime/resource_v3_continuation"
attempt="$(mktemp -d "$task_root/runtime/resource_v3_continuation/attempt.XXXXXX")"
cp -p -- "${BASH_SOURCE[0]}" "$attempt/orchestrator_snapshot.sh"
printf '%s\n' "$attempt"
exec > >(exec 5>&-; tee -a "$attempt/orchestrator.log") 2>&1
trap 'code=$?; printf "%s\n" "$code" > "$attempt/exit_code.txt"' EXIT

primary_worker() {
  local gpu="$1"
  # Wait for the two already-running, task-owned train-only launchers to finish.
  # Drop this observation lock before the worker obtains its own exclusive lock.
  exec 8>"$queue/locks/gpu${gpu}.lock"
  flock 8
  flock -u 8
  exec 8>&-
  exec bash "$scripts/run_matrix_resource_v3.sh" "$gpu"
}

printf '%s\n' 'Waiting for current training, then completing all18 primary jobs.'
primary_worker 0 > "$attempt/primary_gpu0.log" 2>&1 &
primary0=$!
primary_worker 1 > "$attempt/primary_gpu1.log" 2>&1 &
primary1=$!
set +e
wait "$primary0"
code0=$?
wait "$primary1"
code1=$?
set -e
printf '%s %s\n' "$code0" "$code1" > "$attempt/primary_exit_codes.txt"
test "$code0" -eq 0
test "$code1" -eq 0

printf '%s\n' 'All18 primary jobs passed; starting the three pre-registered native repeats.'
(
  set -e
  bash "$scripts/run_native_repeat_resource_v3.sh" P1 0
  bash "$scripts/run_native_repeat_resource_v3.sh" P3 0
) > "$attempt/repeats_gpu0.log" 2>&1 &
repeat0=$!
bash "$scripts/run_native_repeat_resource_v3.sh" P2 1 > "$attempt/repeats_gpu1.log" 2>&1 &
repeat1=$!
set +e
wait "$repeat0"
code0=$?
wait "$repeat1"
code1=$?
set -e
printf '%s %s\n' "$code0" "$code1" > "$attempt/repeat_exit_codes.txt"
test "$code0" -eq 0
test "$code1" -eq 0

printf '%s\n' 'All21 runs passed; sealing candidates before reference evaluation.'
bash "$scripts/runtime/finalize_after_all21.sh" run
printf '%s\n' 'Quantitative outputs and case figures are ready; browser verification and human-facing analysis remain.'
