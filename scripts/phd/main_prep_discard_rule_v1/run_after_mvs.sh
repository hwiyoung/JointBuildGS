#!/usr/bin/env bash
# PHD-MAIN-PREP-DISCARD-RULE-v1: everything after the MVS rebuild (host driver, detached): 5.2 / 5.3 / fork inputs, the fork r11
# dry initialisations (all switches on, then each switch off) on both GPUs, the fork checks, the rule comparison and the figures.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; S="$REPO/scripts/phd/main_prep_discard_rule_v1"
cd "$S"
until grep -q "mvs done" "$P/logs/queue.log"; do sleep 30; done
echo "$(date +%H:%M:%S) after-mvs start" >> "$P/logs/queue.log"
bash run_52.sh ranges gt boxes boxgt b0 forkin
ITEMS="B0_b10:LoD2 B0_b10:ALS B173nb_b10:LoD2 B173nb_b10:ALS B173_b0:LoD2 B173_b0:ALS R1rep_b10:LoD2 R1rep_b10:ALS"
( python3 run_fork.py --gpu 0 --inputs fork_inputs/s52 --tag s52 $ITEMS
  for sw in confidence_mask judgment propagation; do python3 run_fork.py --gpu 0 --inputs fork_inputs/s52 --tag s52 --switch $sw $ITEMS; done ) > "$P/logs/fork_gpu0.log" 2>&1 &
a=$!
( for sw in prior_band protection init_exclusion prior; do python3 run_fork.py --gpu 1 --inputs fork_inputs/s52 --tag s52 --switch $sw $ITEMS; done ) > "$P/logs/fork_gpu1.log" 2>&1 &
b=$!
wait $a; wait $b
echo "fork_checks.py --tag s52 --inputs fork_inputs/s52 --run-sub s52/box" > "$P/logs/jobs_after_a.txt"
echo "rules_eval.py" >> "$P/logs/jobs_after_a.txt"
bash run_queue.sh "$P/logs/jobs_after_a.txt" 2 8 16
printf "site_rows.py\nfigs_main.py\n" > "$P/logs/jobs_after_b.txt"
bash run_queue.sh "$P/logs/jobs_after_b.txt" 2 8 16
echo "$(date +%H:%M:%S) after-mvs done" >> "$P/logs/queue.log"
