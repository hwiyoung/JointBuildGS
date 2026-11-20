#!/usr/bin/env bash
# 11/20 12:33: 공용 칸이 다시 한도를 넘어 가시성 둘이 함께 조여짐 → 하나씩. none·LoD2(도는 중) 끝을 기다린 뒤 A·ALS → A·LoD2 → 판정·채점.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); R="$H/run.sh"; O="$1"
until [[ -f "$O/sight/none/LoD2.complete.json" ]] || ! docker ps --format '{{.Names}}' | grep -q sight_none_LoD2; do sleep 30; done; echo "none LoD2 sight $(date +%H:%M)"
for mp in "A ALS" "A LoD2"; do set -- $mp; bash "$R" sight_${1}_$2 --cpus 2 --mem 12 mf3_sight.py $1 $2 2>&1 | grep -E "SIGHT|Error|Traceback"; done
[[ $(ls "$O"/sight/*/*.complete.json | wc -l) -eq 4 ]] || { echo "SIGHT INCOMPLETE"; exit 1; }; echo "sight done $(date +%H:%M)"
for p in LoD2 ALS; do bash "$R" judge_$p --cpus 4 --mem 30 mf4_judge.py $p none A 2>&1 | grep -E "CHECK|JUDGE|Error|error|Traceback"; done
echo CHAIN_A_DONE $(date +%H:%M)
