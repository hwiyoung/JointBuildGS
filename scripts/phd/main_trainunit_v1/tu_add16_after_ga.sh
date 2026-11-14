#!/usr/bin/env bash
# Addendum 16 stage A. Host memory cannot hold a campus training and a mesh job together, so:
#  1. hold campusef120k_ALS_s0 and B173nbef_ALS_s1 (claim directories; the queues skip claimed runs);
#  2. wait until no tu_ef_queue.py runs (the 판 가 queue ends after campusef30k_ALS_s0, retries included);
#  3. post-process campusef30k_ALS_s0 site by site with the unchanged GTJUDGE steps (tolerance merge for the known roundoff stop);
#  4. release campusef120k_ALS_s0 and start a queue on each GPU (the first GPU with no compute process takes 판 나).
#   bash tu_add16_after_ga.sh > <log> 2>&1
set -u
here=$(cd "$(dirname "$0")" && pwd)
cd "$here"
TU=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1
EF=$TU/runs/ef
K=campusef30k_ALS_s0
for n in campusef120k_ALS_s0 B173nbef_ALS_s1; do
  mkdir -p "$EF/$n"
  mkdir "$EF/$n/claim" && echo "hold $n $(date +%T)" || { echo "claim of $n exists: stop"; exit 1; }
done
while pgrep -f "python3 tu_ef_queue.py" >/dev/null; do sleep 120; done
echo "queues ended $(date +%T)"
st=$(python3 -c "import json;print(json.load(open('$EF/$K/receipt.json'))['status'])" 2>/dev/null || echo NONE)
echo "$K $st"
[ "$st" = TRAINING_COMPLETE ] || { echo "no result: no post, holds kept"; exit 1; }
python3 tu_post.py run $K 1 > "$TU/logs/post-$K.log" 2>&1; echo "post exit $? $(date +%T)"
for s in B0_b10 R1rep_b10 B173nb_b10; do
  if [ ! -f "$TU/gt/scenes/${s}__ALS/distances/$K.npz" ]; then
    python3 tu_post_fix.py $K $s ALS > "$TU/logs/postfix-$K-$s.log" 2>&1; echo "post fix $s exit $? $(date +%T)"
  fi
  [ -f "$TU/gt/scenes/${s}__ALS/distances/$K.npz" ] || { echo "no score $s: holds kept"; exit 1; }
done
rmdir "$EF/campusef120k_ALS_s0/claim" && echo "release campusef120k_ALS_s0 $(date +%T)"
for g in 1 0; do
  nohup python3 tu_ef_queue.py $g > "$TU/logs/queue16b-gpu$g.log" 2>&1 &
  sleep 5
done
echo "stage A done $(date +%T)"
