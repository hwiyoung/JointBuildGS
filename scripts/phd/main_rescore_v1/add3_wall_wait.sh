#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1/addendum3_stage1
# Reuse the slot released by the ALS primary queue; never inspect FINALTRAIN queues.
while [[ ! -f "$OUT/scores/B173nb_b10__ALS__oracle/values.json" ]]; do sleep 30; done
bash "$REPO/scripts/phd/main_rescore_v1/add3_wall_queue.sh"
