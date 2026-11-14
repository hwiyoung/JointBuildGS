#!/usr/bin/env bash
# Addendum 15 after training: wait until no tu_ef_queue.py runs, then post-process R1repef_ALS_s1 (family ef_s1; tolerance
# merge if the known copy-coordinate roundoff stop happens), then the read-out (where with ef_s1, rule quantities).
#   bash tu_add15_after.sh > <log> 2>&1
set -u
here=$(cd "$(dirname "$0")" && pwd)
cd "$here"
TU=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1
S=$TU/gt/scenes/R1rep_b10__ALS/distances/ef_s1.npz
while pgrep -f "python3 tu_ef_queue.py" >/dev/null; do sleep 120; done
echo "queues ended $(date +%T)"
st=$(python3 -c "import json;print(json.load(open('$TU/runs/ef/R1repef_ALS_s1/receipt.json'))['status'])" 2>/dev/null || echo NONE)
echo "R1repef_ALS_s1 $st"
[ "$st" = TRAINING_COMPLETE ] || { echo "no result: no post"; exit 1; }
python3 tu_post.py run efs1_R1rep_b10_ALS 1 > "$TU/logs/post-efs1_R1rep_b10_ALS.log" 2>&1; echo "post exit $? $(date +%T)"
if [ ! -f "$S" ]; then
  python3 tu_post_fix.py efs1_R1rep_b10_ALS R1rep_b10 ALS > "$TU/logs/postfix-efs1_R1rep_b10_ALS.log" 2>&1; echo "post fix exit $? $(date +%T)"
fi
[ -f "$S" ] || { echo "no score"; exit 1; }
bash run_cpu_guarded.sh 20 add15-where 4 24g tu_add15.py where > "$TU/logs/add15-where-final.log" 2>&1; echo "where exit $? $(date +%T)"
bash run_cpu_guarded.sh 20 add15-rule 4 16g tu_add15.py rule > "$TU/logs/add15-rule.log" 2>&1; echo "rule exit $? $(date +%T)"
echo "after done $(date +%T)"
