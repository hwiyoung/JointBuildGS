#!/usr/bin/env bash
# 묶음 가 사슬: 방법 A 살아남은 화소 → 패치 값(none·A) → 가시성(none·A) → 판정·채점. 큰 구역부터.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); R="$H/run.sh"
TILES_BIG="6909_53361 6909_53359 6908_53359 6908_53360 6910_53361 6909_53360 6910_53360 6908_53361 6909_53362 6910_53362 6910_53359 6911_53362 6910_53363 6909_53358 6909_53363 6911_53361 6908_53362 6908_53358 6907_53359 6911_53360 6907_53360 6910_53358 6911_53363 6912_53362"
[[ -f "$1/masks/A.npy" ]] || bash "$R" survA --cpus 4 --mem 16 mf1_surviveA.py campus | grep -v "^points\|depth loaded" | tail -5
( bash "$R" patch_none --cpus 8 --mem 24 mf2_patch.py none $TILES_BIG > /dev/null 2>&1; echo "none patches done" ) &
bash "$R" patch_A --cpus 48 --mem 30 mf2_patch.py A $TILES_BIG > /dev/null 2>&1; echo "A patches done"
wait
for m in none A; do for p in LoD2 ALS; do bash "$R" sight_${m}_$p --cpus 8 --mem 30 mf3_sight.py $m $p | grep SIGHT; done; done
for p in LoD2 ALS; do bash "$R" judge_$p --cpus 4 --mem 30 mf4_judge.py $p none A | grep "CHECK\|JUDGE\|Error\|error"; done
echo CHAIN_A_DONE
