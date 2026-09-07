#!/usr/bin/env bash
# Reattach downstream work without restarting either live native training.
set -euo pipefail
geogs_ce_region="${1:?P1 P2}"
case "$geogs_ce_region" in P1) geogs_ce_gpu=0; geogs_ce_attempt=no_anchor_sfm_memory_recovery_v2 ;; P2) geogs_ce_gpu=1; geogs_ce_attempt=no_anchor_sfm_memory_recovery_P2_v2 ;; *) exit 2 ;; esac
geogs_ce_code="${2:?absolute code directory}"
geogs_ce_task="${3:?absolute task directory}"
geogs_ce_log="$geogs_ce_task/orchestration_recovery_v1/$geogs_ce_region"
geogs_ce_run="$geogs_ce_task/$geogs_ce_attempt/runs/$geogs_ce_region/SFM_noanchor_D005_Pnative"
geogs_ce_container="jbgs-geogs-${geogs_ce_attempt}-${geogs_ce_region}-train"
printf '%s\n' "$$" > "$geogs_ce_log/supervisor.pid"
date -u +%FT%TZ > "$geogs_ce_log/started_utc.txt"
trap 'geogs_ce_exit=$?; printf "%s\n" "$geogs_ce_exit" > "$geogs_ce_log/supervisor_exit_code.txt"' EXIT
printf '%s\n' WAITING_NATIVE_TRAINING > "$geogs_ce_log/status.txt"
while [[ ! -s "$geogs_ce_run/receipt.json" ]] || docker inspect "$geogs_ce_container" >/dev/null 2>&1; do
  sleep 10
done
docker run --rm --network none --cpus 1 --memory 256m --memory-swap 256m \
  --user "$(id -u):$(id -g)" --mount "type=bind,src=$geogs_ce_run/receipt.json,dst=/receipt.json,readonly" \
  sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e \
  python -c 'import json; r=json.load(open("/receipt.json")); print(r["status"]); assert r["status"]=="PASS" and r["native_exit_code"]==0 and r["validated_exit_code"]==0'
for geogs_ce_iter in 22000 30000; do
  printf '%s\n' "EXPORTING_$geogs_ce_iter" > "$geogs_ce_log/status.txt"
  flock "$geogs_ce_task/no_anchor_sfm_v1/locks/heavy_cpu.lock" \
    bash "$geogs_ce_code/run_phase.sh" "$geogs_ce_region" export "$geogs_ce_gpu" "$geogs_ce_iter" "$geogs_ce_attempt"
  printf '%s\n' "EVALUATING_$geogs_ce_iter" > "$geogs_ce_log/status.txt"
  bash "$geogs_ce_code/evaluate.sh" "$geogs_ce_region" "$geogs_ce_iter" seal "$geogs_ce_gpu" "$geogs_ce_attempt"
  flock "$geogs_ce_task/no_anchor_sfm_v1/locks/heavy_cpu.lock" \
    bash "$geogs_ce_code/evaluate.sh" "$geogs_ce_region" "$geogs_ce_iter" geometry "$geogs_ce_gpu" "$geogs_ce_attempt"
  bash "$geogs_ce_code/evaluate.sh" "$geogs_ce_region" "$geogs_ce_iter" renders "$geogs_ce_gpu" "$geogs_ce_attempt"
  bash "$geogs_ce_code/evaluate.sh" "$geogs_ce_region" "$geogs_ce_iter" summary "$geogs_ce_gpu" "$geogs_ce_attempt"
done
printf '%s\n' READY_FOR_VIEWER_AND_REVIEW > "$geogs_ce_log/status.txt"
