#!/usr/bin/env bash
# PHD-MAIN-STAGE1-v1: GPU steps one after another on one GPU (each item "<tag>:<mode>:<site>:<arg>"); stops at the first failure.
#   GPU=0 bash gpu_queue.sh item [item ...]
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
for it in "$@"; do
  IFS=: read -r tag mode site arg <<< "$it"
  GPU=${GPU:-0} bash "$HERE/run_gpu.sh" "$tag" "$mode" "$site" "$arg" || { echo "$(date +%H:%M:%S) gpu_queue failed at $tag: queue stopped" >> "$HERE/../../../../JointBuildGS-artifacts/phase-payloads/phd/main_stage1_v1/PHD-MAIN-STAGE1-v1/logs/queue.log"; exit 1; }
done
