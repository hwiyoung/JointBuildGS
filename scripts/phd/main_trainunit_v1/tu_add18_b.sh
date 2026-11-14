#!/usr/bin/env bash
# Addendum 18, part B: wait for the 판 가 queue started by tu_add18_a.sh, then post campusef30k_ALS_s0 and redo tables and figures.
#   bash tu_add18_b.sh > <log> 2>&1
set -u
here=$(cd "$(dirname "$0")" && pwd)
cd "$here"
TU=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1
EF=$TU/runs/ef
eval "$(sed -n '/^status()/,/^waitq()/p' tu_add18_a.sh)"
while pgrep -f "python3 tu_ef_queue.py" >/dev/null; do sleep 120; done; echo "queue ended $(date +%T)"
st=$(status campusef30k_ALS_s0); echo "campusef30k_ALS_s0 $st"
if [ "$st" = TRAINING_COMPLETE ]; then
  post campusef30k_ALS_s0 1
  for s in B0_b10 R1rep_b10 B173nb_b10; do fixed campusef30k_ALS_s0 campusef30k_ALS_s0 $s; done
  tables final
fi
echo "part B done $(date +%T)"
