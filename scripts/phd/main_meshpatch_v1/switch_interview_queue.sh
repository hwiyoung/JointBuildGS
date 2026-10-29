#!/usr/bin/env bash
# Exact own controller only; the independently running worker finishes normally.
set -euo pipefail
task_repo=$(cd "$(dirname "$0")/../../.." && pwd)
task_out=$(realpath "$task_repo/../JointBuildGS-artifacts/phase-payloads/phd/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1")
task_worker=${1:?exact currently running meshpatch worker container}
[[ "$task_worker" == jbgs-meshpatch-mesh-R1rep_b10__ALS__prop_ALS_s1 || "$task_worker" == jbgs-meshpatch-axes-R1rep_b10__ALS__prop_ALS_s1 ]]
systemctl --user stop jbgs-meshpatch-finalize.service
docker pause jbgs-meshpatch-queue
while docker inspect --format '{{.State.Running}}' "$task_worker" 2>/dev/null | rg -q '^true$'; do sleep 5; done
docker unpause jbgs-meshpatch-queue
docker stop --time 1 jbgs-meshpatch-queue
docker rename jbgs-meshpatch-queue "jbgs-meshpatch-queue-before-interview-$(date +%Y%m%dT%H%M%S)"
bash "$task_repo/scripts/phd/main_meshpatch_v1/start_services.sh" queue
if systemctl --user cat jbgs-meshpatch-finalize.service >/dev/null 2>&1; then
  systemctl --user restart jbgs-meshpatch-finalize.service
else
  systemd-run --user --unit=jbgs-meshpatch-finalize --collect /bin/bash "$task_repo/scripts/phd/main_meshpatch_v1/finalize_when_ready.sh"
fi
date -Is > "$task_out/status/interview_queue_switched.txt"
