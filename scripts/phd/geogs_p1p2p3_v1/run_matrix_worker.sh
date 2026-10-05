#!/usr/bin/env bash
# One worker per GPU; dependencies and exact-anchor gates precede every branch.
set -euo pipefail
gpu="${1:?GPU 0 or 1}"
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
if [[ -s "$task_root/contracts/extraction_resource_v3.json" ]]; then
  exec bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_matrix_resource_v3.sh" "$gpu"
fi
source "$repo_root/scripts/phd/geogs_p1p2p3_v1/runtime_paths.sh"
queue="$queue_root"
mkdir -p "$queue/claims" "$queue/done" "$queue/failed" "$queue/locks"
test -s "$task_root/contracts/runtime_gate_v1.json"
exec 9>"$queue/locks/gpu${gpu}.lock"
flock -n 9
printf '%s\n' "Worker GPU$gpu acquired its task-local lock"
conditions=(D005_Pnative D0005_Pnative D0_Pnative D005_Prelease D0005_Prelease D0_Prelease)
while true; do
  if compgen -G "$queue/failed/*" >/dev/null; then
    printf '%s\n' "A preserved task failure requires review; GPU$gpu starts no further jobs"
    exit 1
  fi
  found=0
  for region in P1 P2 P3; do
    for condition in "${conditions[@]}"; do
      job="${region}_${condition}"
      [[ -e "$queue/done/$job" || -e "$queue/claims/$job" ]] && continue
      if [[ "$condition" == D005_Pnative ]]; then
        if [[ "$region" == P2 && ! -s "$runs_root/P1/D005_Pnative/train_receipt.json" ]]; then continue; fi
        if [[ "$region" == P3 && ! -s "$runs_root/P2/D005_Pnative/train_receipt.json" ]]; then continue; fi
      else
        [[ -s "$runs_root/$region/D005_Pnative/model/jbgs_complete/iteration_8100/receipt.json" ]] || continue
      fi
      available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
      # This protects the preexisting services. It never changes a model setting.
      [[ "$available_kib" -ge 25165824 ]] || continue
      if ! mkdir "$queue/claims/$job" 2>/dev/null; then continue; fi
      found=1
      printf '%s\n' "GPU$gpu starting $job"
      set +e
      (
        set -e
        if [[ "$condition" != D005_Pnative || ( "$runtime_revision" == allocator_v2 && "$region" == P1 ) ]]; then
          bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/ensure_regional_anchor.sh" "$region" "$gpu"
        fi
        for phase in train render metrics auxiliary; do
          bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_regional_phase.sh" "$region" "$condition" "$phase" "$gpu"
        done
      ) > "$queue/claims/$job/run.log" 2>&1
      code=$?
      set -e
      if [[ "$code" -ne 0 ]]; then
        printf '%s\n' "$code" > "$queue/failed/$job"
        printf '%s\n' "GPU$gpu FAILED $job (exit$code); preserved log $queue/claims/$job/run.log"
        tail -n 15 "$queue/claims/$job/run.log"
        exit "$code"
      fi
      touch "$queue/done/$job"
      printf '%s\n' "GPU$gpu completed $job"
      break 2
    done
  done
  completed="$(find "$queue/done" -maxdepth 1 -type f | wc -l)"
  if [[ "$completed" -eq 18 ]]; then
    printf '%s\n' "All18 registered runs and surface/render phases completed"
    exit 0
  fi
  if [[ "$found" -eq 0 ]]; then sleep 5; fi
done
