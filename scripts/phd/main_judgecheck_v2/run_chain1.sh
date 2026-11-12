#!/usr/bin/env bash
# 본값 판 사슬: 고리 R1.5 끝 → r·σ_W·L → 시선 검사(LoD2, ALS) + 사진 준비(구역 둘씩) → 고리 민감도(1.0·3.0) 시작
set -uo pipefail
cd "$(dirname "$0")/../../.."
ART=$(realpath ../JointBuildGS-artifacts); OUT=$ART/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2
until grep -q "RING_ALL_DONE base" $OUT/logs/ring_base_driver.out; do sleep 20; done
bash scripts/phd/main_judgecheck_v2/run.sh calib_base s2_calibrate.py base > /dev/null 2>&1 && echo "CALIB_BASE_OK $(date +%H:%M)" || { echo "CALIB_BASE_FAIL"; exit 1; }
( bash scripts/phd/main_judgecheck_v2/run.sh sight_ALS --cpus 2 --mem 24 s2_sight.py ALS > /dev/null 2>&1; echo "SIGHT_ALS_EXIT $? $(date +%H:%M)" ) &
( bash scripts/phd/main_judgecheck_v2/run.sh sight_LoD2 --cpus 2 --mem 32 s2_sight.py LoD2 > /dev/null 2>&1; echo "SIGHT_LoD2_EXIT $? $(date +%H:%M)" ) &
bash scripts/phd/main_judgecheck_v2/run_pool.sh prep 2 --cpus 2 --mem 24 -- s3_photo_prepare.py
echo "PREP_DONE $(date +%H:%M)"
wait
echo "CHAIN1_DONE $(date +%H:%M)"
