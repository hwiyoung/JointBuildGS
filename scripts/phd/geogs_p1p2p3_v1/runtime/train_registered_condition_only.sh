#!/usr/bin/env bash
# A registered anchor branch may train while independent extraction is repaired.
set -euo pipefail
region="${1:?P1 P2 P3}"
condition="${2:?Registered non-baseline condition}"
gpu="${3:?GPU 0 or 1}"
case "$region" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$condition" in D0005_Pnative|D0_Pnative|D005_Prelease|D0005_Prelease|D0_Prelease) ;; *) exit 2 ;; esac
case "$gpu" in 0|1) ;; *) exit 2 ;; esac
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
export JBGS_RUNTIME_REVISION=allocator_v2
queue="$task_root/queue_allocator_v2"
job="${region}_${condition}"
exec 9>"$queue/locks/gpu${gpu}.lock"
flock -n 9
available_kib="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
[[ "$available_kib" -ge 25165824 ]]
test ! -e "$task_root/runs_allocator_v2/$region/$condition"
test ! -e "$queue/done/$job"
mkdir "$queue/claims/$job"
cp -p "${BASH_SOURCE[0]}" "$queue/claims/$job/train_only_launcher_snapshot.sh"
printf '%s\n' "Registered $job train only on GPU$gpu; post-training phases await extraction resource review. This is not a completed job." > "$queue/claims/$job/scheduling_note.txt"
exec > "$queue/claims/$job/run.log" 2>&1
bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/ensure_regional_anchor.sh" "$region" "$gpu"
exec bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_regional_phase.sh" "$region" "$condition" train "$gpu"
