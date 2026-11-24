#!/bin/bash
# Post-processing watcher v2 (host): a run is (re)scored when its base extraction is scored and the score json is missing or older than any of its
# extraction scores (so occl10 / occlga are added when they arrive). df9 (5.1/5.2) each time; df13 (floating) and df11 (split surface, two-layer)
# once per run (base mesh only); then df14 tables.
cd "$(dirname "$0")"; O=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_depthfix_v1/PHD-MAIN-DEPTHFIX-v1
while true; do
  did=0
  for r in $O/runs/*/p*_s*/; do
    stem=$(basename $(dirname $r)); run=$(basename $r); b=$O/meshes/${stem}__df_${run}_base/score.json; s=$O/score/${stem}__${run}.json
    [ -f $b ] || continue
    new=0; [ -f $s ] || new=1
    for v in base occl10 occlga; do f=$O/meshes/${stem}__df_${run}_${v}/score.json; [ -f $f ] && [ -f $s ] && [ $f -nt $s ] && new=1; done
    [ $new = 1 ] || continue
    echo "$(date -Is) post $stem $run" >> $O/logs/post.log
    python3 launch.py cpu df9_score.py $stem $run >> $O/logs/post.log 2>&1
    [ -f $O/float/${stem}__${run}.json ] || python3 launch.py cpu df13_float.py $stem $run >> $O/logs/post.log 2>&1
    [ -f $O/surface/${stem}__${run}.json ] || python3 launch.py cpu df11_surface.py $stem $run >> $O/logs/post.log 2>&1
    did=1
  done
  [ $did = 1 ] && python3 launch.py cpu df14_tables.py >> $O/logs/post.log 2>&1
  sleep 120
done
