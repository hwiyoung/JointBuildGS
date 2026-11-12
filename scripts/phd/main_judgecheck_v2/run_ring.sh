#!/usr/bin/env bash
# 고리 셈 구동: run_ring.sh <mode> <workers> ; 구역을 차례로(한 구역 점을 workers가 나눠 씀)
set -uo pipefail
cd "$(dirname "$0")/../../.."
OUT=$(realpath ../JointBuildGS-artifacts)/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2
mode=$1; workers=$2
until grep -q GEOM_ALL_DONE "$OUT/logs/geom_driver.out" 2>/dev/null; do sleep 20; done
tiles=$(python3 -c "import json;print(' '.join(t['id'] for t in json.load(open('$(realpath ../JointBuildGS-artifacts)/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/tiles.json'))))")
for t in $tiles; do
  [[ -f "$OUT/ring/$mode/$t.json" ]] && continue
  ls "$OUT/geometry_raw/${t}__"*.npz >/dev/null 2>&1 || continue
  while (( $(free | awk '/^Mem|^메모리/{print int($3*100/$2)}') > 80 )); do sleep 60; done
  bash scripts/phd/main_judgecheck_v2/run.sh ring_${mode}_$t --cpus $workers s1_ring.py $mode $t > /dev/null 2>&1 || bash scripts/phd/main_judgecheck_v2/run.sh ring_${mode}_${t}_retry --cpus $workers s1_ring.py $mode $t > /dev/null 2>&1 || echo "RING_FAIL $mode $t"
  echo "RING_TILE $mode $t $(date +%H:%M)"
done
echo "RING_ALL_DONE $mode"
