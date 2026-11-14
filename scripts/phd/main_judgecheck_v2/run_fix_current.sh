#!/usr/bin/env bash
# 11/14 고침: 세 지역 지금 판 짝짓기를 기둥 규칙으로 → 그것을 쓰는 것만 다시 냄. 한 번에 하나.
set -uo pipefail
cd "$(dirname "$0")/../../.."
R=scripts/phd/main_judgecheck_v2/run.sh
step(){ name=$1; mem=$2; shift 2; bash $R fx_$name --cpus 4 --mem $mem "$@" > /dev/null 2>&1; rc=$?; echo "STEP $name $rc $(date +%H:%M)"; [[ $rc == 0 ]] || { echo FIX_FAILED; exit 1; }; }
step truth_exp 16 s4_truth_exp.py
step assemble_LoD2 32 s6_assemble.py LoD2
step assemble_ALS 32 s6_assemble.py ALS
step tables 32 s7_tables.py
step checks 32 s8_checks.py LoD2 ALS
step fig4 8 s10_charts.py fig4
step export 32 s9_export.py
echo FIX_DONE
