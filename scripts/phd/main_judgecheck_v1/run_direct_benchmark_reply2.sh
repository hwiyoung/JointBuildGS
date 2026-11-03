#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$REPO"
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1
while true; do
  set +e
  bash scripts/phd/main_judgecheck_v1/run_gpu_guarded_reply2.sh maxdirect photo_score_direct_reply2.py
  result=$?
  set -e
  [[ "$result" == 0 ]] && break
  [[ "$result" == 3 ]] || exit "$result"
  printf '%s\twait_before_start\twhole tile benchmark\n' "$(date -Is)" >> "$OUT/r2/resources/direct_benchmark_gpu_wait.tsv"
  sleep 30
done
