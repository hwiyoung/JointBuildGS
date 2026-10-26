#!/usr/bin/env bash
# Stop only this task's exact container after a complete tile receipt is durable.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
out=$(realpath "$repo/../JointBuildGS-artifacts/phase-payloads/phd/main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1")
container=$1
tile=$2
cmd=$(docker inspect -f '{{json .Config.Cmd}}' "$container")
[[ "$cmd" == *'/repo/scripts/phd/main_photocheck_v1/run_measure.py'* && "$cmd" == *'full'* ]]
while [[ ! -f "$out/work/full/${tile}.npz" || ! -f "$out/work/full/${tile}.json" ]]; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$container")" == true ]]
  sleep 5
done
printf '%s\n' "$(date -Iseconds) checkpoint $tile complete; restarting exact container $container for verified RAM cache" >> "$out/logs/checkpoint_restart.log"
docker stop --time 10 "$container"
