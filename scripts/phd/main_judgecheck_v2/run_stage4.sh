#!/usr/bin/env bash
# 단계 4: 그림 5 → 그림 7 → 패치·참값 점·사진 점·학습용 판정 파일 내보내기. 한 번에 하나.
set -uo pipefail
cd "$(dirname "$0")/../../.."
OUT=$(realpath ../JointBuildGS-artifacts)/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2; R=scripts/phd/main_judgecheck_v2/run.sh
step(){ name=$1; mem=$2; shift 2; bash $R st4_$name --cpus 2 --mem $mem "$@" > /dev/null 2>&1; echo "STEP $name $? $(date +%H:%M)"; }
step fig5 24 s10_images.py fig5
step fig7 24 s10_images.py fig7
step export 32 s9_export.py
echo STAGE4_DONE
