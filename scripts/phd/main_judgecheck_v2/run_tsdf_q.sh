#!/usr/bin/env bash
# 사분면 TSDF 구동: 통째 메시가 있거나 통째 셈이 도는 구역은 건너뛰고(도는 것은 끝난 뒤 다시 봄) 두 구역씩.
set -uo pipefail
cd "$(dirname "$0")/../../.."
ART=$(realpath ../JointBuildGS-artifacts); OUT=$ART/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2
tiles=$(python3 -c "import json;print(' '.join(t['id'] for t in json.load(open('$ART/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/tiles.json'))))")
for pass in 1 2 3; do
  for t in $tiles; do
    [[ -f $OUT/truth/mvs_surface/$t.npz || -f $OUT/truth/mvs_surface/${t}_q3.npz ]] && continue
    docker ps --format '{{.Names}}' | grep -q "^jbgs-judgecheck2-tsdf_${t}$" && continue
    while (( $(jobs -rp | wc -l) >= 2 )); do sleep 10; done
    while (( $(free | awk 'NR==2{print int($3*100/$2)}') > 80 )); do sleep 60; done
    ( bash scripts/phd/main_judgecheck_v2/run.sh tsdfq_$t --cpus 4 --mem 16 --image jointbuildgs:geogs-conf-guided-v1 s1_tsdf_q.py $t > /dev/null 2>&1 || echo "TSDFQ_FAIL $t"; echo "TSDFQ_TILE $t $(date +%H:%M)" ) &
    sleep 5
  done
  wait
  while docker ps --format '{{.Names}}' | grep -q "^jbgs-judgecheck2-tsdf_"; do sleep 30; done
done
echo TSDFQ_ALL_DONE
