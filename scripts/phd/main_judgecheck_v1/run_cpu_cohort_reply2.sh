#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$REPO"
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1
group=$1
parent=$2
active_tile=$3
active_name="jbgs-judgecheck-cpu_photo${group}_$active_tile"
[[ "$(ps -p "$parent" -o args=)" == 'bash scripts/phd/main_judgecheck_v1/run_census_adaptive_reply2.sh '* ]]
[[ "$(docker inspect -f '{{.State.Running}}' "$active_name")" == true ]]
[[ "$group" == 1 || "$group" == 2 ]]
if [[ "$group" == 2 ]]; then [[ -f "$OUT/r2/reports/roof_commit.json" ]]; fi
# Pause only this task's shell coordinator. Its active Docker calculation keeps
# running; the second replacement worker waits for that calculation to finish.
first=''
second=''
cleanup() {
  if [[ -n "$first" ]]; then wait "$first" 2>/dev/null || true; fi
  if [[ -n "$second" ]]; then wait "$second" 2>/dev/null || true; fi
  kill -CONT "$parent" 2>/dev/null || true
}
trap cleanup EXIT
kill -STOP "$parent"
mkdir -p "$OUT/r2/cpu_cohorts/group$group"
printf '%s\tcoordinator_paused\t%s\t%s\n' "$(date -Is)" "$parent" "$active_tile" >> "$OUT/r2/cpu_cohorts/group$group/events.tsv"
bash scripts/phd/main_judgecheck_v1/run_cpu_reply2_aux.sh "cohort${group}_setup" cpu_cohort_reply2.py setup "$group" "$active_tile"
bash scripts/phd/main_judgecheck_v1/run_cpu_reply2_aux.sh "cohort${group}_audit" audit_source_reply2.py
wait_memory() {
  while (( $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo) < 37748736 )); do
    printf '%s\twait_memory_below_36GiB\n' "$(date -Is)" >> "$OUT/r2/cpu_cohorts/group$group/events.tsv"
    sleep 5
  done
}
wait_memory
bash scripts/phd/main_judgecheck_v1/run_cpu_photo_worker_reply2.sh "$group" 0 &
first=$!
while [[ "$(docker inspect -f '{{.State.Running}}' "$active_name" 2>/dev/null || true)" == true ]]; do sleep 5; done
wait_memory
bash scripts/phd/main_judgecheck_v1/run_cpu_photo_worker_reply2.sh "$group" 1 &
second=$!
set +e
wait "$first"; first_status=$?
wait "$second"; second_status=$?
set -e
[[ "$first_status" == 0 && "$second_status" == 0 ]]
bash scripts/phd/main_judgecheck_v1/run_cpu_reply2_aux.sh "cohort${group}_verify" cpu_cohort_reply2.py verify "$group"
printf '%s\tcoordinator_resumed\t%s\n' "$(date -Is)" "$parent" >> "$OUT/r2/cpu_cohorts/group$group/events.tsv"
kill -CONT "$parent"
trap - EXIT
