#!/usr/bin/env bash
set -euo pipefail
geogs_lc_region="${1:?P1 P2}"
case "$geogs_lc_region" in P1|P2) ;; *) exit 2 ;; esac
geogs_lc_code=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
geogs_lc_repo=$(cd -- "$geogs_lc_code/../../../.." && pwd)
geogs_lc_task=$(realpath "$geogs_lc_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_lc_out="$geogs_lc_task/orchestration_recovery_v1/$geogs_lc_region"
test ! -e "$geogs_lc_out"
mkdir -p -- "$geogs_lc_out"
cp -- "${BASH_SOURCE[0]}" "$geogs_lc_code/continue_existing_v2.sh" "$geogs_lc_out/"
setsid nohup bash "$geogs_lc_out/continue_existing_v2.sh" "$geogs_lc_region" "$geogs_lc_code" "$geogs_lc_task" \
  < /dev/null > "$geogs_lc_out/stdout.log" 2> "$geogs_lc_out/stderr.log" &
printf '%s\n' "$!" > "$geogs_lc_out/launched_pid.txt"
printf 'Launched detached %s continuation\n' "$geogs_lc_region"
