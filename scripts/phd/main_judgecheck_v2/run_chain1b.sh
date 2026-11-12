#!/usr/bin/env bash
# 본값 판 사슬(메모리 확인 판): 시선 검사(ALS, LoD2) + 사진 준비(구역 둘씩) → 이어서 MVS 면(사분면, 한 구역씩)
set -uo pipefail
cd "$(dirname "$0")/../../.."
ART=$(realpath ../JointBuildGS-artifacts); OUT=$ART/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2
memwait(){ while (( $(free | awk 'NR==2{print int($3*100/$2)}') > ${1:-78} )); do sleep 30; done; }
memwait; ( bash scripts/phd/main_judgecheck_v2/run.sh sight_ALS --cpus 2 --mem 24 s2_sight.py ALS > /dev/null 2>&1; echo "SIGHT_ALS_EXIT $? $(date +%H:%M)" ) &
sleep 60; memwait; ( bash scripts/phd/main_judgecheck_v2/run.sh sight_LoD2 --cpus 2 --mem 32 s2_sight.py LoD2 > /dev/null 2>&1; echo "SIGHT_LoD2_EXIT $? $(date +%H:%M)" ) &
sleep 60; memwait; bash scripts/phd/main_judgecheck_v2/run_pool.sh prep 2 --cpus 2 --mem 24 -- s3_photo_prepare.py
echo "PREP_DONE $(date +%H:%M)"
wait
echo "CHAIN1_DONE $(date +%H:%M)"
