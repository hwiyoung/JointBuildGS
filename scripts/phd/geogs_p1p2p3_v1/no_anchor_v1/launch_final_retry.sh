#!/usr/bin/env bash
set -euo pipefail
geogs_fr_region="${1:?P1 P2 P3}"
geogs_fr_gpu="${2:?0 or 1}"
case "$geogs_fr_region" in P1|P2|P3) ;; *) exit 2 ;; esac
case "$geogs_fr_gpu" in 0|1) ;; *) exit 2 ;; esac
geogs_fr_code=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
geogs_fr_repo=$(cd -- "$geogs_fr_code/../../../.." && pwd)
geogs_fr_task=$(realpath "$geogs_fr_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_fr_attempt="no_anchor_sfm_gradient_memory_v3_$geogs_fr_region"
geogs_fr_out="$geogs_fr_task/$geogs_fr_attempt/detached_run_v1"
test -s "$geogs_fr_task/$geogs_fr_attempt/amendment.json"
test ! -e "$geogs_fr_out"
test ! -e "$geogs_fr_task/$geogs_fr_attempt/runs/$geogs_fr_region/SFM_noanchor_D005_Pnative"
mkdir -p -- "$geogs_fr_out"
cp -- "${BASH_SOURCE[0]}" "$geogs_fr_code/run_final_retry_detached.sh" "$geogs_fr_out/"
date -u +%FT%TZ > "$geogs_fr_out/queued_utc.txt"
setsid nohup bash "$geogs_fr_out/run_final_retry_detached.sh" \
  "$geogs_fr_code" "$geogs_fr_task" "$geogs_fr_region" "$geogs_fr_gpu" \
  < /dev/null > "$geogs_fr_out/stdout.log" 2> "$geogs_fr_out/stderr.log" &
printf '%s\n' "$!" > "$geogs_fr_out/launched_pid.txt"
printf '%s\n' "Detached final resource retry supervisor launched for $geogs_fr_region on GPU $geogs_fr_gpu"
