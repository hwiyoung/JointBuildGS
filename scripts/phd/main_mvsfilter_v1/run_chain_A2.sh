#!/usr/bin/env bash
# 묶음 가 사슬 다시 걸기(11/20 10:40): 공용 docker-workloads 묶음 memory.high(60 GiB)에 닿아 두 컨테이너가 8시간 조여짐 → 한 번에 하나만.
# A 패치 → none 패치(원통만 다시 셈, 고리 u_M 은 저장 값; 재현 표본은 앞 세 구역에서 끝남) → 가시성 → 판정·채점.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); R="$H/run.sh"
TILES_BIG="6909_53361 6909_53359 6908_53359 6908_53360 6910_53361 6909_53360 6910_53360 6908_53361 6909_53362 6910_53362 6910_53359 6911_53362 6910_53363 6909_53358 6909_53363 6911_53361 6908_53362 6908_53358 6907_53359 6911_53360 6907_53360 6910_53358 6911_53363 6912_53362"
bash "$R" patch_A --cpus 48 --mem 30 mf2_patch.py A $TILES_BIG 2>&1 | grep -E "^PATCH|Error|error|Traceback|waiting" | cut -c1-160; echo "A patches done $(date +%H:%M)"
MF_RING_REPRO=0 bash "$R" patch_none --cpus 16 --mem 16 mf2_patch.py none $TILES_BIG 2>&1 | grep -E "Error|error|Traceback|waiting" | cut -c1-160; echo "none patches done $(date +%H:%M)"
for m in none A; do for p in LoD2 ALS; do bash "$R" sight_${m}_$p --cpus 8 --mem 30 mf3_sight.py $m $p 2>&1 | grep -E "SIGHT|Error|Traceback|waiting"; done; done; echo "sight done $(date +%H:%M)"
for p in LoD2 ALS; do bash "$R" judge_$p --cpus 4 --mem 30 mf4_judge.py $p none A 2>&1 | grep -E "CHECK|JUDGE|Error|error|Traceback"; done
echo CHAIN_A_DONE $(date +%H:%M)
