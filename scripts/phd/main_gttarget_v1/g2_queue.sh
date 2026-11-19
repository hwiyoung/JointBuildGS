#!/bin/bash
# Stage 2 queue (order 6.2): six runs in order on one GPU, then the two optional seed-1 runs. usage: g2_queue.sh <gpu>
cd "$(dirname "$0")"
for s in R1rep_b10__ALS R1rep_b10__LoD2 B0_b10__LoD2 B173nb_b10__LoD2 B173nb_b10__ALS B0_b10__ALS; do
  [ -f ../../../../JointBuildGS-artifacts/phase-payloads/phd/main_gttarget_v1/PHD-MAIN-GTTARGET-v1/runs/$s/gtt_s0/receipt.json ] || python3 launch.py train $s $1 0
done
for s in R1rep_b10__ALS R1rep_b10__LoD2; do
  [ -f ../../../../JointBuildGS-artifacts/phase-payloads/phd/main_gttarget_v1/PHD-MAIN-GTTARGET-v1/runs/$s/gtt_s1/receipt.json ] || python3 launch.py train $s $1 1
done
echo QUEUE_DONE
