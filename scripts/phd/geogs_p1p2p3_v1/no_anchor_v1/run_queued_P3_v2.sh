#!/usr/bin/env bash
# P3 enters GPU0 only after the entire selected P1 worker closes.
set -euo pipefail
geogs_qp_code=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
geogs_qp_repo=$(cd -- "$geogs_qp_code/../../../.." && pwd)
geogs_qp_task=$(realpath "$geogs_qp_repo/../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1")
geogs_qp_wait="$geogs_qp_task/no_anchor_sfm_memory_recovery_P3_v2/lane_wait"
test ! -e "$geogs_qp_wait"
test -f "$geogs_qp_task/no_anchor_sfm_memory_recovery_P3_v2/amendment.json"
mkdir -p -- "$geogs_qp_wait"
cp -- "${BASH_SOURCE[0]}" "$geogs_qp_wait/launcher_snapshot.sh"
date -u +%FT%TZ > "$geogs_qp_wait/queued_utc.txt"
trap 'geogs_qp_exit=$?; printf "%s\n" "$geogs_qp_exit" > "$geogs_qp_wait/exit_code.txt"' EXIT
while [[ ! -f "$geogs_qp_task/no_anchor_sfm_memory_recovery_v2/queue/P1/exit_code.txt" ]]; do
  sleep 10
done
date -u +%FT%TZ > "$geogs_qp_wait/started_utc.txt"
bash "$geogs_qp_code/run_region.sh" P3 0 no_anchor_sfm_memory_recovery_P3_v2
