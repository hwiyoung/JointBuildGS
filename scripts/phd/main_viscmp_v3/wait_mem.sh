#!/usr/bin/env bash
# PHD-MAIN-VISCMP-v3: wait before a big read: host MemAvailable >= 30 GB and no GPU post step of the fix-test task (jbgs-ftg-*).
# Polls every 60 s; writes the waited seconds to logs/waits.log.   bash wait_mem.sh <tag>
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); VC="$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_viscmp_v3/PHD-MAIN-VISCMP-v3"
tag=${1:-step}; need=${NEED_GB:-30}; t0=$SECONDS; why=""
while true; do
  avail=$(awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo)
  post=$(docker ps --format '{{.Names}}' | grep -c '^jbgs-ftg-' || true)
  if [ "$avail" -ge "$need" ] && [ "$post" -eq 0 ]; then break; fi
  why="avail=${avail}GB ftg=${post}"; sleep 60
done
echo "$(date '+%m-%d %H:%M:%S') $tag waited=$((SECONDS-t0))s last_reason=${why:-none} avail_at_start=$(awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo)GB" >> "$VC/logs/waits.log"
