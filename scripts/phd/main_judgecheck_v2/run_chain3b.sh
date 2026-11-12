#!/usr/bin/env bash
# 고리 민감도(1.0·3.0, 56 일꾼) → 같은 면 고리 ; 나란히: MVS 면(tsdfq_early)이 끝나면 참값 점(구역 둘씩)
set -uo pipefail
cd "$(dirname "$0")/../../.."
ART=$(realpath ../JointBuildGS-artifacts); OUT=$ART/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2
memwait(){ while (( $(free | awk 'NR==2{print int($3*100/$2)}') > ${1:-78} )); do sleep 30; done; }
( bash scripts/phd/main_judgecheck_v2/run_ring.sh sens 56; echo "SENS_DRIVER_END $(date +%H:%M)"
  for t in $(ls $OUT/geometry_raw/*__LoD2.npz | xargs -n1 basename | sed 's/__LoD2.npz//'); do
    [[ -f $OUT/ring/face/$t.json ]] && continue; memwait
    bash scripts/phd/main_judgecheck_v2/run.sh ringface_$t --cpus 56 s1_ring_face.py $t > /dev/null 2>&1 || bash scripts/phd/main_judgecheck_v2/run.sh ringface_${t}_retry --cpus 56 s1_ring_face.py $t > /dev/null 2>&1 || echo "FACE_FAIL $t"; echo "FACE_TILE $t $(date +%H:%M)"; done
  echo "FACE_ALL_DONE $(date +%H:%M)" ) &
( until grep -q TSDFQ_EARLY_DONE $OUT/logs/tsdfq_early.out; do sleep 30; done
  for t in $(ls $OUT/geometry_raw/*__LoD2.npz | xargs -n1 basename | sed 's/__LoD2.npz//'); do
    [[ -f $OUT/truth/rest/$t.json ]] && continue
    while (( $(jobs -rp | wc -l) >= 2 )); do sleep 15; done; memwait
    ( bash scripts/phd/main_judgecheck_v2/run.sh truth_$t --cpus 8 --mem 28 s4_truth_rest.py $t > /dev/null 2>&1 || echo "TRUTH_FAIL $t"; echo "TRUTH_TILE $t $(date +%H:%M)" ) &
    sleep 5
  done; wait; echo "TRUTH_ALL_DONE $(date +%H:%M)" ) &
wait; echo "CHAIN3_DONE $(date +%H:%M)"
