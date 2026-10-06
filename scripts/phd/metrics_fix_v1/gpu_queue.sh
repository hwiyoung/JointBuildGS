#!/usr/bin/env bash
# PHD-MAIN-METRICS-FIX-v1 4.7: the GPU steps one after another (TSDF host memory). A failed step is recorded and the queue stops.
#   GPU=0 bash gpu_queue.sh option1:b1_LoD2 option1:b2_LoD2 ...
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
for item in "$@"; do
  bash "$HERE/run_gpu.sh" "${item%%:*}" "${item##*:}" || { echo "$(date +%H:%M:%S) $item failed: queue stopped" >> "$HERE/../../../../JointBuildGS-artifacts/phase-payloads/phd/metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1/logs/queue.log"; exit 1; }
done
