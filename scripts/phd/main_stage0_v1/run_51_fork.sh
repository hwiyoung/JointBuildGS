#!/usr/bin/env bash
# PHD-MAIN-STAGE0-v1 5.1 (host driver): fork r12 dry initialisations, two GPUs in parallel, then the checks.
#   GPU 0: the four boxes x LoD2 (rule auto = current), the four boxes x ALS with rule current, the seven switches x LoD2 (B173nb_b10)
#   GPU 1: the four boxes x ALS (rule auto = margin_all_2), the seven switches x ALS (B173nb_b10)
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
P="$ART/phase-payloads/phd/main_stage0_v1/PHD-MAIN-STAGE0-v1"; S="$REPO/scripts/phd/main_stage0_v1"
cd "$S"
I=fork_inputs/s61; T=s61; SITE=B173nb_b10
SWS="confidence_mask judgment propagation prior_band protection init_exclusion prior"
(
  python3 run_fork_v6.py --gpu 0 --inputs $I --tag $T B0_b10:LoD2 B173nb_b10:LoD2 B173_b0:LoD2 R1rep_b10:LoD2
  python3 run_fork_v6.py --gpu 0 --inputs $I --tag $T --rule current B0_b10:ALS B173nb_b10:ALS B173_b0:ALS R1rep_b10:ALS
  for s in $SWS; do python3 run_fork_v6.py --gpu 0 --inputs $I --tag $T --switch $s $SITE:LoD2; done
) > "$P/logs/fork_51_gpu0.log" 2>&1 &
(
  python3 run_fork_v6.py --gpu 1 --inputs $I --tag $T B0_b10:ALS B173nb_b10:ALS B173_b0:ALS R1rep_b10:ALS
  for s in $SWS; do python3 run_fork_v6.py --gpu 1 --inputs $I --tag $T --switch $s $SITE:ALS; done
) > "$P/logs/fork_51_gpu1.log" 2>&1 &
wait
echo "$(date +%H:%M:%S) fork dry inits done" >> "$P/logs/queue.log"
echo "fork_checks_v6.py --tag $T --inputs $I --run-sub s61/box" > "$P/logs/jobs_51/checks.txt"
echo "compare_51.py" >> "$P/logs/jobs_51/checks.txt"
bash run_queue.sh "$P/logs/jobs_51/checks.txt" 2 8 24
