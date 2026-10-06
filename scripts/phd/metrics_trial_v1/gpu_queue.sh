#!/usr/bin/env bash
# PHD-MAIN-METRICS-TRIAL-v1: the GPU steps of the four stage-0 trainings, one at a time (TSDF host memory), after any GPU step
# of this task still running. A run killed for memory (rc 137: the container cap) is redone once at voxel 0.10 m (config
# virtual_view_mesh.fallback) and recorded in logs/gpu_fallback.txt.
#   GPU=0 bash gpu_queue.sh b1_LoD2 b1_ALS b2_LoD2 b2_ALS
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$(realpath "$HERE/../../../../JointBuildGS-artifacts/phase-payloads/phd/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1")
while docker ps --format '{{.Names}}' | grep -q '^jbgs-mt-gpu_'; do sleep 20; done
for run in "$@"; do
  bash "$HERE/run_gpu.sh" run "$run"; rc=$?
  if [ $rc -eq 137 ]; then
    echo "$(date +%H:%M:%S) $run: memory cap reached at voxel 0.05 m (rc 137) -> voxel 0.10 m" | tee -a "$OUT/logs/gpu_fallback.txt"
    bash "$HERE/run_gpu.sh" run "$run" --voxel 0.10; rc=$?
  fi
  if [ $rc -ne 0 ]; then echo "$(date +%H:%M:%S) $run failed rc=$rc: queue stopped" | tee -a "$OUT/logs/queue.log"; exit $rc; fi
done
