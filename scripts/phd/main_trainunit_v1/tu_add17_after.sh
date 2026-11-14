#!/usr/bin/env bash
# Addendum 17 after 판 가 (replaces tu_add16_after_ga.sh; 판 나 is not run and its claim directory stays as a hold).
# Host memory cannot hold a training next to mesh jobs, so the steps run one after another:
#  1. wait until no tu_ef_queue.py runs (판 가 ends, retries included);
#  2. post-process campusef30k_ALS_s0 site by site if it finished (tolerance merge for the known roundoff stop);
#  3. release B173nbef_ALS_s1 and start a queue on each GPU (new code: cellsef_ALS_s0_cell1fix first, then B173nbef_ALS_s1;
#     the queue rules decide GPU and host memory); wait until the queues end;
#  4. merge 판 다 with the new cell 1 (cellsef1fix) and post-process R1rep_b10 only; post-process B173nbef_ALS_s1;
#  5. tables (tu_add16.py table, cellfix, fig) and the filter figures of the three boxes (tu_figures.py <site> ALS ef).
#   bash tu_add17_after.sh > <log> 2>&1
set -u
here=$(cd "$(dirname "$0")" && pwd)
cd "$here"
TU=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1
EF=$TU/runs/ef
status() { python3 -c "import json;print(json.load(open('$EF/$1/receipt.json'))['status'])" 2>/dev/null || echo NONE; }
post() {  # key, workers, sites (comma), sites to check
  local key=$1; shift
  python3 tu_post.py run "$key" "$@" > "$TU/logs/post-$key.log" 2>&1; echo "post $key exit $? $(date +%T)"
}
fixed() {  # key family site
  local f="$TU/gt/scenes/${3}__ALS/distances/$2.npz"
  if [ ! -f "$f" ]; then
    python3 tu_post_fix.py "$1" "$3" ALS > "$TU/logs/postfix-$1-$3.log" 2>&1; echo "post fix $1 $3 exit $? $(date +%T)"
  fi
  [ -f "$f" ] && echo "score $2 $3 ok" || echo "NO SCORE $2 $3"
}
[ -d "$EF/campusef120k_ALS_s0/claim" ] || { echo "120k hold missing: stop"; exit 1; }
[ -d "$EF/B173nbef_ALS_s1/claim" ] || { echo "B173nbef_ALS_s1 hold missing: stop"; exit 1; }
while pgrep -f "python3 tu_ef_queue.py" >/dev/null; do sleep 120; done
echo "queues ended $(date +%T)"
st=$(status campusef30k_ALS_s0); echo "campusef30k_ALS_s0 $st"
if [ "$st" = TRAINING_COMPLETE ]; then
  post campusef30k_ALS_s0 1
  for s in B0_b10 R1rep_b10 B173nb_b10; do fixed campusef30k_ALS_s0 campusef30k_ALS_s0 $s; done
else
  echo "판 가 has no result: no post"
fi
rmdir "$EF/B173nbef_ALS_s1/claim" && echo "release B173nbef_ALS_s1 $(date +%T)"
for g in 1 0; do
  nohup python3 tu_ef_queue.py $g > "$TU/logs/queue17-gpu$g.log" 2>&1 &
  sleep 5
done
sleep 60
while pgrep -f "python3 tu_ef_queue.py" >/dev/null; do sleep 120; done
echo "queues ended $(date +%T)"
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
bash run_cpu_guarded.sh 20 add16-table 4 16g tu_add16.py table > "$TU/logs/add16-table-final.log" 2>&1; echo "table exit $? $(date +%T)"
bash run_cpu_guarded.sh 20 add17-cellfix 4 24g tu_add16.py cellfix > "$TU/logs/add17-cellfix.log" 2>&1; echo "cellfix exit $? $(date +%T)"
bash run_cpu_guarded.sh 20 add16-fig 2 6g tu_add16.py fig > "$TU/logs/add16-fig-final.log" 2>&1; echo "fig exit $? $(date +%T)"
for s in B0_b10 R1rep_b10 B173nb_b10; do
  bash run_cpu_guarded.sh 20 fig-ef-$(echo $s | tr '_' '-' | tr 'A-Z' 'a-z') 4 32g tu_figures.py $s ALS ef > "$TU/logs/fig-ef-$s.log" 2>&1; echo "figures $s exit $? $(date +%T)"
done
echo "after done $(date +%T)"
