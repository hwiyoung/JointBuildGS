#!/usr/bin/env bash
# PHD-MAIN-BASE151-v1: replace the running queue by the current b151_host.py code without touching the running cell
# (TRAINUNIT-v2 lesson: a running queue keeps its old code). QUEUE_STOP makes the old queue return after its running cell; then the
# new queue starts.   nohup bash relaunch_queue.sh <old_pid> > OUT/logs/relaunch.log 2>&1 &
# scientific_verdict: null
set -u
D=$(cd "$(dirname "$0")" && pwd)
OUT=$(realpath "$D/../../../../JointBuildGS-artifacts")/phase-payloads/phd/main_base151_v1/PHD-MAIN-BASE151-v1
old=$1
touch "$OUT/control/QUEUE_STOP"
while kill -0 "$old" 2>/dev/null; do sleep 30; done
rm -f "$OUT/control/QUEUE_STOP"
cd "$D" && nohup python3 b151_host.py queue >> "$OUT/logs/queue.log" 2>&1 &
echo "$(date '+%F %T') old queue $old ended; new queue $!"
