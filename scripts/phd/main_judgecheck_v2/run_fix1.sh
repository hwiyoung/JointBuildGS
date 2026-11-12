#!/usr/bin/env bash
# 관리기에서 실패로 남은 일 다시: 6912_53362 참값 점(빈 구역) → 6909_53361 MVS 면 16칸 → 그 구역 참값 점 → 조립 LoD2·ALS. 한 번에 하나(관리기 몫 + 이 일 <= 80 GB).
set -uo pipefail
cd "$(dirname "$0")/../../.."
R=scripts/phd/main_judgecheck_v2/run.sh
memwait(){ while (( $(free | awk 'NR==2{print int($3*100/$2)}') > 75 )); do sleep 30; done; }
memwait; bash $R fix_truth_6912_53362 --cpus 2 --mem 8 s4_truth_rest.py 6912_53362 > /dev/null 2>&1; echo "TRUTH_6912_53362 $? $(date +%H:%M)"
memwait; bash $R fix_tsdf16_6909_53361 --cpus 4 --mem 16 --image jointbuildgs:geogs-conf-guided-v1 s1_tsdf_s16.py 6909_53361 > /dev/null 2>&1; echo "TSDF16_6909_53361 $? $(date +%H:%M)"
memwait; bash $R fix_truth_6909_53361 --cpus 8 --mem 20 s4_truth_rest_s16.py 6909_53361 > /dev/null 2>&1; echo "TRUTH_6909_53361 $? $(date +%H:%M)"
for p in LoD2 ALS; do memwait; bash $R fix_assemble_$p --cpus 2 --mem 32 s6_assemble.py $p > /dev/null 2>&1; echo "ASSEMBLE_$p $? $(date +%H:%M)"; done
echo FIX1_DONE
