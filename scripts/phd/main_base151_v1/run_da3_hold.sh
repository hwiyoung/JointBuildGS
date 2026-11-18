#!/usr/bin/env bash
# PHD-MAIN-BASE151-v1: hold the queue (control/HOLD_GPU), wait until no training container of this task runs on GPU 1, run DA3 for the
# four cells (run_da3.sh, sequentially), release the hold. One cell at a time on GPU 1 is kept: DA3 runs only between two cells.
#   nohup bash run_da3_hold.sh > OUT/logs/da3_hold.log 2>&1 &
# scientific_verdict: null
set -u
D=$(cd "$(dirname "$0")" && pwd)
OUT=$(realpath "$D/../../../../JointBuildGS-artifacts")/phase-payloads/phd/main_base151_v1/PHD-MAIN-BASE151-v1
touch "$OUT/control/HOLD_GPU"
echo "$(date '+%F %T') HOLD_GPU set"
while docker ps --format '{{.Names}}' | grep -q '^jbgs-b151-train-'; do sleep 30; done
echo "$(date '+%F %T') no training container; DA3 starts"
for k in 0 1 2 3; do
  if [ -f "$OUT/da3/geogs/cell$k/da3_prior_consec12/receipt.json" ]; then continue; fi
  bash "$D/run_da3.sh" "$k"
done
rm -f "$OUT/control/HOLD_GPU"
echo "$(date '+%F %T') HOLD_GPU released"
