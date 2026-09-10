#!/usr/bin/env bash
# Preserve original failed attempt; use the frozen worker after the main queue.
set -euo pipefail
region=${1:?region}
condition=${2:?condition}
attempt_id=${3:?new attempt ID}
(( $# == 3 ))
[[ $region =~ ^P[123]$ && $condition =~ ^LC_D(005|0005|0)_P(native|release)$ ]]
[[ $attempt_id =~ ^[A-Za-z0-9_]+_attempt[2-9][0-9]*$ ]]
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1")
queue="$task_root/main_v2/queue"
retry_queue="$task_root/main_v2/retry_queue/$attempt_id"
output_relative="main_v2/retries/$attempt_id"
test -s "$queue/started.txt"
test -s "$task_root/main_v2/runs/$region/$condition/train_receipt.json"
[[ ! -e $retry_queue && ! -e $task_root/$output_relative ]]
mkdir -p "$retry_queue"
cp -- "${BASH_SOURCE[0]}" "$retry_queue/retry_after_queue_v2.sh"
event() { printf '%s %s\n' "$(date --iso-8601=seconds)" "$*" >> "$retry_queue/events.log"; }
image=sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e
[[ $(docker image inspect jointbuildgs:geogs-official-db40c95-compat-v1 --format '{{.Id}}') == "$image" ]]
docker run --rm --network none --read-only --cpus 1 --memory 256m --memory-swap 256m \
 --mount "type=bind,src=$task_root/main_v2/runs/$region/$condition/train_receipt.json,dst=/failed.json,readonly" \
 "$image" python -c 'import json; r=json.load(open("/failed.json")); assert r["status"]=="FAIL" and r["phase"]=="train" and r["scientific_verdict"] is None' \
 > "$retry_queue/failed_status_check.log" 2>&1
event "REQUESTED $region $condition gpu=1 output=$output_relative same_frozen_policy=true"
# Main and retry orchestration cannot own the execution resource at once.
exec 9>"$queue/owner.lock"
until flock -n 9; do sleep 30; done
test -s "$queue/model_phases_exit_code.txt"
event 'MAIN_QUEUE_ENDED_EXCLUSIVE_LOCK_ACQUIRED'
available_gib() { awk '/MemAvailable:/{print int($2/1024/1024)}' /proc/meminfo; }
idle_gpu() {
 local gpu=$1 used utilization
 used=$(nvidia-smi -i "$gpu" --query-gpu=memory.used --format=csv,noheader,nounits)
 utilization=$(nvidia-smi -i "$gpu" --query-gpu=utilization.gpu --format=csv,noheader,nounits)
 (( used < 1800 && utilization < 10 ))
}
until (( $(available_gib) >= 38 )) && idle_gpu 0 && idle_gpu 1; do
 event "RESOURCE_WAIT mem_available_gib=$(available_gib)"
 sleep 30
done
free_kib=$(df --output=avail "$task_root" | tail -n 1)
(( free_kib >= 104857600 ))
bash "$repo/scripts/phd/local_complementary_refinement_v1/capture_environment_v2.sh" "before_retry_$attempt_id"
runner="$repo/scripts/phd/local_complementary_refinement_v1/run_phase_v2.sh"
for phase in train render metrics; do
 event "${phase}_START $region $condition gpu=1"
 if bash "$runner" "$region" "$condition" "$phase" 1 "$output_relative" > "$retry_queue/${phase}.log" 2>&1; then
  event "${phase}_PASS $region $condition"
 else
  event "${phase}_FAIL $region $condition preserve_failed_attempt"
  printf '1\n' > "$retry_queue/exit_code.txt"
  exit 1
 fi
done
event "RETRY_COMPLETE $region $condition"
printf '0\n' > "$retry_queue/exit_code.txt"
