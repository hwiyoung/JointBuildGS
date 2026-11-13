#!/usr/bin/env bash
# 단계 3: 단계 2 끝 → 참값 표 다시 조립(민감도 판 열 넣음, 사전 정보마다 하나씩) → 확인 2·3·4 → 그림 4. 한 번에 하나.
set -uo pipefail
cd "$(dirname "$0")/../../.."
OUT=$(realpath ../JointBuildGS-artifacts)/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2; R=scripts/phd/main_judgecheck_v2/run.sh
until grep -q STAGE2_DONE $OUT/logs/stage2.out; do sleep 30; done
step(){ name=$1; mem=$2; shift 2; bash $R st3_$name --cpus 2 --mem $mem "$@" > /dev/null 2>&1; echo "STEP $name $? $(date +%H:%M)"; }
step assemble_LoD2 32 s6_assemble.py LoD2
step assemble_ALS 32 s6_assemble.py ALS
step checks 32 s8_checks.py LoD2 ALS
step fig4 8 s10_charts.py fig4
echo STAGE3_DONE
