#!/usr/bin/env bash
# Addendum 18, part A (replaces tu_add17_after.sh): one training at a time on GPU 1, core comparison set first.
#  1. hold 판 가 (claim directory), release B173nbef_ALS_s1, one queue on GPU 1: cellsef_ALS_s0_cell1fix, then B173nbef_ALS_s1;
#  2. merge 판 다 with the new cell 1 and post R1rep_b10; post B173nbef_ALS_s1; tables and figures (core set);
#  3. release 판 가 and start its queue on GPU 1 (attempt 2), then exit. Part B (tu_add18_b.sh) waits for it and posts.
#   bash tu_add18_a.sh > <log> 2>&1
set -u
here=$(cd "$(dirname "$0")" && pwd)
cd "$here"
TU=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1
EF=$TU/runs/ef
status() { python3 -c "import json;print(json.load(open('$EF/$1/receipt.json'))['status'])" 2>/dev/null || echo NONE; }
post() { local key=$1; shift; python3 tu_post.py run "$key" "$@" > "$TU/logs/post-$key.log" 2>&1; echo "post $key exit $? $(date +%T)"; }
fixed() {  # key family site
  local f="$TU/gt/scenes/${3}__ALS/distances/$2.npz"
  if [ ! -f "$f" ]; then python3 tu_post_fix.py "$1" "$3" ALS > "$TU/logs/postfix-$1-$3.log" 2>&1; echo "post fix $1 $3 exit $? $(date +%T)"; fi
  [ -f "$f" ] && echo "score $2 $3 ok" || echo "NO SCORE $2 $3"
}
tables() {  # tag
  bash run_cpu_guarded.sh 20 add16-table 4 16g tu_add16.py table > "$TU/logs/add16-table-$1.log" 2>&1; echo "table exit $? $(date +%T)"
  bash run_cpu_guarded.sh 20 add17-cellfix 4 24g tu_add16.py cellfix > "$TU/logs/add17-cellfix-$1.log" 2>&1; echo "cellfix exit $? $(date +%T)"
  bash run_cpu_guarded.sh 20 add16-fig 2 6g tu_add16.py fig > "$TU/logs/add16-fig-$1.log" 2>&1; echo "fig exit $? $(date +%T)"
  for s in B0_b10 R1rep_b10 B173nb_b10; do
    bash run_cpu_guarded.sh 20 fig-ef-$(echo $s | tr '_' '-' | tr 'A-Z' 'a-z') 4 32g tu_figures.py $s ALS ef > "$TU/logs/fig-ef-$s-$1.log" 2>&1; echo "figures $s exit $? $(date +%T)"
  done
}
waitq() { sleep 60; while pgrep -f "python3 tu_ef_queue.py" >/dev/null; do sleep 120; done; echo "queue ended $(date +%T)"; }
pgrep -f "python3 tu_ef_queue.py" >/dev/null && { echo "a queue already runs: stop"; exit 1; }
[ -d "$EF/campusef120k_ALS_s0/claim" ] || { echo "120k record claim missing: stop"; exit 1; }
mkdir "$EF/campusef30k_ALS_s0/claim" && echo "hold 판 가 $(date +%T)" || { echo "cannot hold 판 가: stop"; exit 1; }
rmdir "$EF/B173nbef_ALS_s1/claim" && echo "release B173nbef_ALS_s1 $(date +%T)"
nohup python3 tu_ef_queue.py 1 > "$TU/logs/queue18-gpu1-a.log" 2>&1 &
waitq
st=$(status cellsef_ALS_s0_cell1fix); echo "cellsef_ALS_s0_cell1fix $st"
if [ "$st" = TRAINING_COMPLETE ]; then
  bash run_cpu_guarded.sh 20 merge-cellsef1fix-als 8 48g tu_postcpu.py merge ALS cellsef1fix > "$TU/logs/merge-cellsef1fix_ALS_s0.log" 2>&1; echo "merge exit $? $(date +%T)"
  post cellsef1fix_ALS_s0 1 R1rep_b10
  fixed cellsef1fix_ALS_s0 cellsef1fix_ALS_s0 R1rep_b10
fi
st=$(status B173nbef_ALS_s1); echo "B173nbef_ALS_s1 $st"
if [ "$st" = TRAINING_COMPLETE ]; then
  post efs1_B173nb_b10_ALS 1
  fixed efs1_B173nb_b10_ALS ef_s1 B173nb_b10
fi
tables core
echo "core done $(date +%T)"
rmdir "$EF/campusef30k_ALS_s0/claim" && echo "release 판 가 $(date +%T)"
nohup python3 tu_ef_queue.py 1 > "$TU/logs/queue18-gpu1-b.log" 2>&1 &
sleep 30
pgrep -af "python3 tu_ef_queue.py" | head -2
echo "part A done $(date +%T)"
