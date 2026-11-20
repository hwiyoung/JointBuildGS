#!/usr/bin/env bash
# 묶음 나 사슬: 방법 B(Wolff 두 판)·C(통계적) 살아남은 화소 → 패치 값 → 가시성(하나씩: 공용 메모리 칸) → 판정·채점(none·A·B·C) → 표 → 점검 → 그림.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); R="$H/run.sh"; O="$1"
TILES_BIG="6909_53361 6909_53359 6908_53359 6908_53360 6910_53361 6909_53360 6910_53360 6908_53361 6909_53362 6910_53362 6910_53359 6911_53362 6910_53363 6909_53358 6909_53363 6911_53361 6908_53362 6908_53358 6907_53359 6911_53360 6907_53360 6910_53358 6911_53363 6912_53362"
st() { echo "$1 $(date +%H:%M)"; }
[[ -f "$O/masks/B_orig.npy" ]] || bash "$R" wolff --cpus 32 --mem 16 mf5_wolff.py 32 2>&1 | grep -E "WOLFF|Error|Traceback|error"; st "B masks"
[[ -f "$O/masks/C.npy" ]] || bash "$R" stat --cpus 16 --mem 24 mf6_stat.py 2>&1 | grep -E "STAT|Error|Traceback|error" | tail -5; st "C mask"
for m in B_orig B_view C; do [[ -f "$O/masks/$m.npy" ]] || { echo "MASK MISSING $m"; exit 1; }; done
for m in B_orig B_view C; do bash "$R" patch_$m --cpus 48 --mem 30 mf2_patch.py $m $TILES_BIG 2>&1 | grep -E "Error|Traceback" | head -5; st "patch $m $(ls $O/patch/$m/*.npz | wc -l)"; done
for m in B_orig B_view C; do for p in ALS LoD2; do bash "$R" sight_${m}_$p --cpus 2 --mem 12 mf3_sight.py $m $p 2>&1 | grep -E "SIGHT|Error|Traceback"; done; done
[[ $(ls "$O"/sight/*/*.complete.json | wc -l) -eq 10 ]] || { echo "SIGHT INCOMPLETE"; exit 1; }; st "sight done"
for p in LoD2 ALS; do bash "$R" judge_$p --cpus 4 --mem 30 mf4_judge.py $p none A B_orig B_view C 2>&1 | grep -E "CHECK|JUDGE|Error|error|Traceback"; done
bash "$R" tables_B --cpus 8 --mem 24 mf7_tables.py A B_orig B_view C 2>&1 | grep -E "Error|Traceback"
bash "$R" checks_B --cpus 4 --mem 16 mf7b_checks.py A B_orig B_view C 2>&1 | grep -E "CHECK|Error|Traceback" | cut -c1-300
echo CHAIN_B_DONE $(date +%H:%M)
