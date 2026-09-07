#!/usr/bin/env bash
# Continue one already registered learning condition while extraction is reviewed.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
task_root="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1"
export JBGS_RUNTIME_REVISION=allocator_v2
queue="$task_root/queue_allocator_v2"
job=P1_D0_Pnative
exec 9>"$queue/locks/gpu0.lock"
flock -n 9
test ! -e "$task_root/runs_allocator_v2/P1/D0_Pnative"
test ! -e "$queue/done/$job"
mkdir "$queue/claims/$job"
cp -p "${BASH_SOURCE[0]}" "$queue/claims/$job/train_only_launcher_snapshot.sh"
printf '%s\n' 'Registered P1 D0_Pnative train only; remaining phases await extraction resource review. This is not a completed job.' > "$queue/claims/$job/scheduling_note.txt"
exec > "$queue/claims/$job/run.log" 2>&1
bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/ensure_regional_anchor.sh" P1 0
exec bash "$repo_root/scripts/phd/geogs_p1p2p3_v1/run_regional_phase.sh" P1 D0_Pnative train 0
