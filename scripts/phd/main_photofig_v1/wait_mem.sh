#!/usr/bin/env bash
# PHD-MAIN-PHOTOFIG-v1: wait before a big read (request 2.8): host MemAvailable >= 30 GB and no GPU post step of the fix-test task
# (TSDF mesh extraction and the R1 post run in containers named jbgs-ftg-*; scripts/phd/main_fixtest_v1/run_ft.py:234-242).
# Polls every 60 s; writes the waited seconds to logs/waits.log.   bash wait_mem.sh <tag>
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); PF="$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_photofig_v1/PHD-MAIN-PHOTOFIG-v1"
tag=${1:-step}; need=${NEED_GB:-30}; t0=$SECONDS; why=""
while true; do
  avail=$(awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo)
  post=$(docker ps --format '{{.Names}}' | grep -c '^jbgs-ftg-' || true)
  if [ "$avail" -ge "$need" ] && [ "$post" -eq 0 ]; then break; fi
  why="avail=${avail}GB ftg=${post}"
  sleep 60
done
echo "$(date '+%m-%d %H:%M:%S') $tag waited=$((SECONDS-t0))s last_reason=${why:-none} avail_at_start=$(awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo)GB" >> "$PF/logs/waits.log"
