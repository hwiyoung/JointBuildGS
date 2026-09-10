#!/usr/bin/env bash
# Durable two-GPU queue. Only this task's containers and additive paths are used.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(cd -- "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1" && pwd)
mkdir -p "$task_root/queue"
exec 9>"$task_root/queue/owner.lock"
flock -n 9 || { echo 'This task already has an active queue owner'; exit 2; }
[[ ! -e "$task_root/queue/completed.txt" ]]
[[ -f "$task_root/contracts/execution_ready.json" ]]
phase_runner="$repo/scripts/phd/local_complementary_refinement_v1/run_phase.sh"
printf '%s\n' "$(date --iso-8601=seconds) queue started pid=$$" >> "$task_root/queue/events.log"
wait_resources() {
    local gpu=$1
    while :; do
        local available used utilization
        available=$(awk '/MemAvailable:/{print int($2/1024/1024)}' /proc/meminfo)
        used=$(nvidia-smi -i "$gpu" --query-gpu=memory.used --format=csv,noheader,nounits)
        utilization=$(nvidia-smi -i "$gpu" --query-gpu=utilization.gpu --format=csv,noheader,nounits)
        if (( available >= 28 && used < 1800 && utilization < 10 )); then return; fi
        sleep 30
    done
}
worker() {
    local gpu=$1 protection=$2 failed=0
    for coefficient in 005 0005 0; do
        for region in P2 P1 P3; do
            local condition="LC_D${coefficient}_P${protection}"
            local run="$task_root/runs/$region/$condition"
            if [[ -e "$run/train_receipt.json" || -e "$run/model" ]]; then
                printf '%s\n' "$(date --iso-8601=seconds) REFUSE_EXISTING $region $condition" >> "$task_root/queue/events.log"
                failed=1
                continue
            fi
            wait_resources "$gpu"
            printf '%s\n' "$(date --iso-8601=seconds) TRAIN_START $region $condition GPU=$gpu" >> "$task_root/queue/events.log"
            if ! bash "$phase_runner" "$region" "$condition" train "$gpu" > "$task_root/queue/${region}_${condition}_train.log" 2>&1; then
                printf '%s\n' "$(date --iso-8601=seconds) TRAIN_FAIL $region $condition" >> "$task_root/queue/events.log"
                failed=1
                continue
            fi
            # Serialize extraction to preserve host headroom. Other GPU can train.
            (
                flock 8
                wait_resources "$gpu"
                printf '%s\n' "$(date --iso-8601=seconds) RENDER_START $region $condition GPU=$gpu" >> "$task_root/queue/events.log"
                bash "$phase_runner" "$region" "$condition" render "$gpu" &&
                bash "$phase_runner" "$region" "$condition" metrics "$gpu"
            ) 8>"$task_root/queue/extraction.lock" > "$task_root/queue/${region}_${condition}_render_metrics.log" 2>&1 || {
                printf '%s\n' "$(date --iso-8601=seconds) EXTRACTION_OR_METRICS_FAIL $region $condition" >> "$task_root/queue/events.log"
                failed=1
                continue
            }
            printf '%s\n' "$(date --iso-8601=seconds) CONDITION_PASS $region $condition" >> "$task_root/queue/events.log"
        done
    done
    return "$failed"
}
worker 0 native &
worker0=$!
worker 1 release &
worker1=$!
failed=0
wait "$worker0" || failed=1
wait "$worker1" || failed=1
printf '%s\n' "$(date --iso-8601=seconds) model queue finished failure=$failed" >> "$task_root/queue/events.log"
if (( failed == 0 )); then
    if bash "$repo/scripts/phd/local_complementary_refinement_v1/run_evaluation.sh" > "$task_root/queue/evaluation.log" 2>&1; then
        printf '%s\n' "$(date --iso-8601=seconds) ALL_18_AND_EVALUATION_COMPLETE scientific_verdict=null" > "$task_root/queue/completed.txt"
    else
        printf '%s\n' "$(date --iso-8601=seconds) EVALUATION_FAIL" >> "$task_root/queue/events.log"
        exit 1
    fi
else
    printf '%s\n' "$(date --iso-8601=seconds) PARTIAL_FAILURE inspect receipts; no automatic retry" > "$task_root/queue/partial_failure.txt"
    exit 1
fi
