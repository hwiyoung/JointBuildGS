#!/usr/bin/env bash
# Create only this task's new advisory-lock inode; never replace an existing one.
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
lock_path="$repo_root/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights/.geogs_extraction.lock"
if [[ ! -e "$lock_path" ]]; then
  (set -o noclobber; printf '%s\n' 'Task-local extraction scheduling lock; weight files are unchanged.' > "$lock_path")
fi
test -f "$lock_path"
