#!/usr/bin/env bash
# PHD-MAIN-PREP-DISCARD-RULE-v1 equivalence check 1 (host driver): meshes, stage 1 of the 8 ranges and 4 boxes with module v5, compare.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; S="$REPO/scripts/phd/main_prep_discard_rule_v1"
cd "$S"
echo "$(date +%H:%M:%S) eq1 start" >> "$P/logs/queue.log"
bash run_queue.sh "$P/logs/jobs_eq1_a.txt" 3 8 12
bash run_queue.sh "$P/logs/jobs_eq1_b.txt" 3 10 14
bash run_queue.sh "$P/logs/jobs_eq1_c.txt" 1 4 8
echo "$(date +%H:%M:%S) eq1 done" >> "$P/logs/queue.log"
