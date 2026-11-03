#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$REPO"
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1
[[ -f "$OUT/r2/reports/roof_commit.json" ]]
bash scripts/phd/main_judgecheck_v1/run_cpu.sh streamwalllock photo_stream_score_reply2.py setup
bash scripts/phd/main_judgecheck_v1/run_cpu.sh streamwallplan census_plan_reply2.py
cpu_queue=0
while read -r tile; do
  [[ -f "$OUT/r2/photo_scores/$tile/complete.json" || -f "$OUT/r2/photo_scores/$tile/group2/complete.json" ]] && continue
  set +e
  bash scripts/phd/main_judgecheck_v1/run_gpu_guarded_reply2.sh "streamwall_$tile" photo_stream_score_reply2.py "$tile:2"
  result=$?
  set -e
  [[ "$result" == 0 ]] && continue
  [[ "$result" == 3 ]] || exit "$result"
  cpu_queue=1
  printf '%s\tCPU_queue_selected_other_research_GPU_active\twalls\n' "$(date -Is)" >> "$OUT/r2/resources/cpu_fallback.tsv"
  break
done < "$OUT/r2/census_group2_tiles.txt"
if [[ "$cpu_queue" == 1 ]]; then
  bash scripts/phd/main_judgecheck_v1/run_cpu.sh wallcohortplan cpu_cohort_reply2.py setup 2 none
  bash scripts/phd/main_judgecheck_v1/run_cpu.sh wallcohortaudit audit_source_reply2.py
  first=''; second=''
  cleanup() {
    if [[ -n "$first" ]]; then wait "$first" 2>/dev/null || true; fi
    if [[ -n "$second" ]]; then wait "$second" 2>/dev/null || true; fi
  }
  trap cleanup EXIT
  wait_memory() {
    while (( $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) < 37748736 )); do
      printf '%s\twait_memory_below_36GiB\n' "$(date -Is)" >> "$OUT/r2/cpu_cohorts/group2/events.tsv"
      sleep 5
    done
  }
  wait_memory
  bash scripts/phd/main_judgecheck_v1/run_cpu_photo_worker_reply2.sh 2 0 &
  first=$!
  wait_memory
  bash scripts/phd/main_judgecheck_v1/run_cpu_photo_worker_reply2.sh 2 1 &
  second=$!
  set +e
  wait "$first"; first_status=$?
  wait "$second"; second_status=$?
  set -e
  [[ "$first_status" == 0 && "$second_status" == 0 ]]
  bash scripts/phd/main_judgecheck_v1/run_cpu.sh wallcohortverify cpu_cohort_reply2.py verify 2
  trap - EXIT
fi
# Completed photo files are reused; this executes decisions, tables and report.
bash scripts/phd/main_judgecheck_v1/run_census_adaptive_reply2.sh walls
