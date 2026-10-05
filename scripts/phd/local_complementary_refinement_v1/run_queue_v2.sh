#!/usr/bin/env bash
# Paired sequential scheduling; extraction never overlaps training.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
task_root=$(cd -- "$repo/../JointBuildGS-artifacts/phase-payloads/phd/local_complementary_refinement_v1/PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1" && pwd)
queue="$task_root/main_v2/queue"
mkdir -p "$queue"
exec 9>"$queue/owner.lock"
flock -n 9 || { echo 'Main v2 already has a queue owner'; exit 2; }
[[ ! -e $queue/started.txt && -f $task_root/contracts/main_v2/execution_ready.json ]]
date --iso-8601=seconds > "$queue/started.txt"
runner="$repo/scripts/phd/local_complementary_refinement_v1/run_phase_v2.sh"
event() { printf '%s %s\n' "$(date --iso-8601=seconds)" "$*" >> "$queue/events.log"; }
available_gib() { awk '/MemAvailable:/{print int($2/1024/1024)}' /proc/meminfo; }
idle_gpu() {
    local gpu=$1 used utilization
    used=$(nvidia-smi -i "$gpu" --query-gpu=memory.used --format=csv,noheader,nounits)
    utilization=$(nvidia-smi -i "$gpu" --query-gpu=utilization.gpu --format=csv,noheader,nounits)
    (( used < 1800 && utilization < 10 ))
}
wait_resources() {
    local gpu=$1
    until (( $(available_gib) >= 38 )) && idle_gpu "$gpu"; do
        event "RESOURCE_WAIT gpu=$gpu mem_available_gib=$(available_gib)"
        sleep 30
    done
    local free_kib
    free_kib=$(df --output=avail "$task_root" | tail -n 1)
    (( free_kib >= 104857600 )) || { event 'FAIL_DISK_BELOW_100GIB'; exit 1; }
}
run_phase() {
    local region=$1 condition=$2 phase=$3 gpu=$4
    event "${phase}_START $region $condition gpu=$gpu"
    if bash "$runner" "$region" "$condition" "$phase" "$gpu" > "$queue/${region}_${condition}_${phase}.log" 2>&1; then
        event "${phase}_PASS $region $condition"
    else
        event "${phase}_FAIL $region $condition preserve_failed_run"
        return 1
    fi
}
failed=0
for coefficient in 005 0005 0; do
    for region in P2 P1 P3; do
        native="LC_D${coefficient}_Pnative"; release="LC_D${coefficient}_Prelease"
        wait_resources 0
        wait_resources 1
        pair_failed=0
        if (( $(available_gib) >= 70 )); then
            run_phase "$region" "$native" train 0 & native_pid=$!
            run_phase "$region" "$release" train 1 & release_pid=$!
            wait "$native_pid" || pair_failed=1
            wait "$release_pid" || pair_failed=1
        else
            event "SERIAL_PAIR $region $coefficient reserve_6GiB_available=$(available_gib)"
            run_phase "$region" "$native" train 0 || pair_failed=1
            wait_resources 1
            run_phase "$region" "$release" train 1 || pair_failed=1
        fi
        for protection in native release; do
            condition="LC_D${coefficient}_P${protection}"
            # A failed train never authorizes extraction. The worker validates PASS.
            if [[ -f $task_root/main_v2/runs/$region/$condition/train_receipt.json ]]; then
                wait_resources 1
                run_phase "$region" "$condition" render 1 && run_phase "$region" "$condition" metrics 1 || pair_failed=1
            else
                pair_failed=1
            fi
        done
        event "PAIR_FINISHED $region $coefficient failed=$pair_failed"
        if (( pair_failed != 0 )); then failed=1; fi
    done
done
event "ALL_TRAIN_RENDER_METRICS_FINISHED failed=$failed"
printf '%s\n' "$failed" > "$queue/model_phases_exit_code.txt"
exit "$failed"
