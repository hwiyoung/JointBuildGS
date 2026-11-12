#!/usr/bin/env bash
# 구역 일을 P개씩 나눠 돌림. 새 일을 띄우기 전에 호스트 메모리 80 % 이하인지 본다.
# run_pool.sh <name> <P> <run.sh options...> -- <script.py> [args before tile]
set -uo pipefail
cd "$(dirname "$0")/../../.."
ART=$(realpath ../JointBuildGS-artifacts); OUT=$ART/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2
name=$1; P=$2; shift 2; opts=(); while [[ "$1" != "--" ]]; do opts+=("$1"); shift; done; shift
script=$1; shift; pre=("$@")
tiles=$(python3 -c "import json;print(' '.join(t['id'] for t in json.load(open('$ART/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/tiles.json'))))")
for t in $tiles; do
  while (( $(jobs -rp | wc -l) >= P )); do sleep 10; done
  while (( $(free | awk 'NR==2{print int($3*100/$2)}') > 80 )); do sleep 60; done
  ( bash scripts/phd/main_judgecheck_v2/run.sh ${name}_$t "${opts[@]}" $script "${pre[@]}" $t > /dev/null 2>&1 || bash scripts/phd/main_judgecheck_v2/run.sh ${name}_${t}_retry "${opts[@]}" $script "${pre[@]}" $t > /dev/null 2>&1 || echo "POOL_FAIL $name $t"; echo "POOL_TILE $name $t $(date +%H:%M)" ) &
  sleep 5
done
wait; echo "POOL_ALL_DONE $name"
