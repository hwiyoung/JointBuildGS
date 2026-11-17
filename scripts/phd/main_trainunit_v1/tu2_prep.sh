#!/usr/bin/env bash
# PHD-MAIN-TRAINUNIT-v2: training inputs of the nine 3 x 3 cells (ALS) with the unchanged v1 rules
# (tu_campus.seeds -> maps in 3 parts -> index), one cell after another.   nohup bash tu2_prep.sh > <log> 2>&1 &
set -u
here=$(cd "$(dirname "$0")" && pwd); cd "$here"
TU=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v2
for k in "$@"; do
  [ -f "$TU/stage1/cell${k}__ALS/ready.json" ] && { echo "cell$k ready"; continue; }
  [ -f "$TU/stage1/cell${k}__ALS/seed_receipt.json" ] || bash run2_cpu.sh seeds-cell$k-als 8 32g tu_campus.py seeds cell$k ALS || { echo "seeds cell$k failed"; continue; }
  for p in 0 1 2; do bash run2_cpu.sh maps-cell$k-als-$p 3 14g tu_campus.py maps cell$k ALS $p 3 & done
  wait
  bash run2_cpu.sh index-cell$k-als 4 12g tu_campus.py index cell$k ALS; echo "cell$k index exit $? $(date +%T)"
done
echo "prep done $(date +%T)"
