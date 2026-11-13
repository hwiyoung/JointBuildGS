#!/usr/bin/env bash
# Addendum 14 after training: wait until no tu_ef_queue.py runs, then (if all four cellsef ALS cells are TRAINING_COMPLETE)
# merge them with the unchanged 판 다 rule, post-process the two filter single sites and the merged cells (sites one after
# another), and check the part-A density predictions. Host side; containers via run_cpu_guarded.sh / tu_post.py.
#   nohup bash tu_add14_after.sh > <log> 2>&1 &
set -u
here=$(cd "$(dirname "$0")" && pwd)
cd "$here"
TU=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1
while pgrep -f "python3 tu_ef_queue.py" >/dev/null; do sleep 120; done
echo "queues ended $(date +%T)"
ok=1
for k in 0 1 2 3; do
  st=$(python3 -c "import json;print(json.load(open('$TU/runs/ef/cellsef_ALS_s0_cell$k/receipt.json'))['status'])" 2>/dev/null || echo NONE)
  echo "cell$k $st"
  [ "$st" = TRAINING_COMPLETE ] || ok=0
done
for key in ef_R1rep_b10_ALS ef_B173nb_b10_ALS; do
  python3 tu_post.py run $key > "$TU/logs/post-$key.log" 2>&1; echo "post $key exit $? $(date +%T)"
done
if [ $ok = 1 ]; then
  bash run_cpu_guarded.sh 20 merge-cellsef-als 8 48g tu_postcpu.py merge ALS cellsef > "$TU/logs/merge-cellsef_ALS_s0.log" 2>&1; echo "merge exit $? $(date +%T)"
  python3 tu_post.py run cellsef_ALS_s0 1 > "$TU/logs/post-cellsef_ALS_s0.log" 2>&1; echo "post cellsef exit $? $(date +%T)"
else
  echo "not all cells TRAINING_COMPLETE: no merge"
fi
bash run_cpu_guarded.sh 20 density-check 4 16g tu_density.py check > "$TU/logs/density-check.log" 2>&1; echo "density check exit $? $(date +%T)"
echo "after done $(date +%T)"
