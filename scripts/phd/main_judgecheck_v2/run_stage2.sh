#!/usr/bin/env bash
# 단계 2: 판정 없음 셈 끝 → 표(확인 1·5) → 모임 → 단계 0 표 → 그림 2·3 → 그림 1·캠퍼스 지도 → 그림 6. 한 번에 하나(관리기 고리 20 GB + 이 일 <= 80 GB).
set -uo pipefail
cd "$(dirname "$0")/../../.."
OUT=$(realpath ../JointBuildGS-artifacts)/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2; R=scripts/phd/main_judgecheck_v2/run.sh
until grep -q UNPAIRED_ALL_DONE $OUT/logs/unpaired_driver.out; do sleep 30; done
step(){ name=$1; mem=$2; shift 2; bash $R st2_$name --cpus 2 --mem $mem "$@" > /dev/null 2>&1; echo "STEP $name $? $(date +%H:%M)"; }
step tables 32 s7_tables.py
step clusters 32 s7_clusters.py
step s0pub 24 s0_publish.py
step charts 8 s10_charts.py fig2 fig3
step maps 32 s10_maps.py fig1 campus_map
step fig6 24 s10_images.py fig6
echo STAGE2_DONE
