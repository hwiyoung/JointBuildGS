#!/usr/bin/env bash
# 고리 민감도(1.0·3.0) → 같은 면 고리 ; 나란히 MVS 면 사분면(한 구역씩) → 참값 점(구역 둘씩) → 패치 참값 자리
set -uo pipefail
cd "$(dirname "$0")/../../.."
ART=$(realpath ../JointBuildGS-artifacts); OUT=$ART/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2
memwait(){ while (( $(free | awk 'NR==2{print int($3*100/$2)}') > ${1:-78} )); do sleep 30; done; }
until grep -q PREP_DONE $OUT/logs/chain1b.out; do sleep 30; done
( bash scripts/phd/main_judgecheck_v2/run_ring.sh sens 56; echo "SENS_DRIVER_END $(date +%H:%M)"
  tiles=$(ls $OUT/geometry_raw/*__LoD2.npz | xargs -n1 basename | sed 's/__LoD2.npz//')
  for t in $tiles; do memwait; bash scripts/phd/main_judgecheck_v2/run.sh ringface_$t --cpus 56 s1_ring_face.py $t > /dev/null 2>&1 || bash scripts/phd/main_judgecheck_v2/run.sh ringface_${t}_retry --cpus 56 s1_ring_face.py $t > /dev/null 2>&1 || echo "FACE_FAIL $t"; echo "FACE_TILE $t $(date +%H:%M)"; done
  echo "FACE_ALL_DONE $(date +%H:%M)" ) &
( tiles=$(python3 -c "import json;print(' '.join(t['id'] for t in json.load(open('$ART/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/tiles.json'))))")
  while docker ps --format '{{.Names}}' | grep -q "^jbgs-judgecheck2-tsdf"; do sleep 30; done
  for t in $tiles; do
    [[ -f $OUT/truth/mvs_surface/$t.npz || -f $OUT/truth/mvs_surface/${t}_q3.npz ]] && continue
    memwait; bash scripts/phd/main_judgecheck_v2/run.sh tsdfq_$t --cpus 4 --mem 16 --image jointbuildgs:geogs-conf-guided-v1 s1_tsdf_q.py $t > /dev/null 2>&1 || echo "TSDFQ_FAIL $t"; echo "TSDFQ_TILE $t $(date +%H:%M)"
  done
  echo "TSDF_ALL_DONE $(date +%H:%M)"
  for t in $(ls $OUT/geometry_raw/*__LoD2.npz | xargs -n1 basename | sed 's/__LoD2.npz//'); do
    while (( $(jobs -rp | wc -l) >= 2 )); do sleep 15; done; memwait
    ( bash scripts/phd/main_judgecheck_v2/run.sh truth_$t --cpus 8 --mem 28 s4_truth_rest.py $t > /dev/null 2>&1 || echo "TRUTH_FAIL $t"; echo "TRUTH_TILE $t $(date +%H:%M)" ) &
    sleep 5
  done; wait; echo "TRUTH_ALL_DONE $(date +%H:%M)"
  for t in $(ls $OUT/geometry_raw/*__LoD2.npz | xargs -n1 basename | sed 's/__LoD2.npz//'); do memwait; bash scripts/phd/main_judgecheck_v2/run.sh gtpatch_$t --cpus 24 --mem 24 s4_gt_patch.py $t > /dev/null 2>&1 || echo "GTPATCH_FAIL $t"; done
  echo "GTPATCH_ALL_DONE $(date +%H:%M)" ) &
wait
echo "CHAIN3_DONE $(date +%H:%M)"
