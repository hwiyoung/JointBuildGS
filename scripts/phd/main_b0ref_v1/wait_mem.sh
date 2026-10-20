#!/usr/bin/env bash
# PHD-MAIN-B0REF-v1: wait before a big read or distance step (request 2.8): host MemAvailable >= 30 GB and no GPU post step of the
# fix-test task running (its TSDF mesh extraction and the R1 post run in containers named jbgs-ftg-*, scripts/phd/main_fixtest_v1/
# run_ft.py:234-242, run_gpu_ft.sh:16). Polls every 60 s; writes the waited seconds to logs/waits.log.   bash wait_mem.sh <tag>
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); B0="$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_b0ref_v1/PHD-MAIN-B0REF-v1"
tag=${1:-step}; need=${NEED_GB:-30}; t0=$SECONDS; why=""
while true; do
  avail=$(awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo)
  post=$(docker ps --format '{{.Names}}' | grep -c '^jbgs-ftg-' || true)
  if [ "$avail" -ge "$need" ] && [ "$post" -eq 0 ]; then break; fi
  why="avail=${avail}GB ftg=${post}"
  sleep 60
done
echo "$(date '+%m-%d %H:%M:%S') $tag waited=$((SECONDS-t0))s last_reason=${why:-none} avail_at_start_of_step=$(awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo)GB" >> "$B0/logs/waits.log"
