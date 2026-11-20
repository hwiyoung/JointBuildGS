#!/usr/bin/env bash
# 11/20 11:59: 가시성 검사는 CPU 하나만 씀 → none·LoD2(이미 도는 중) 옆에 나머지 셋을 함께 돌림(공용 칸 29 GB 일 때). 그다음 판정·채점.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); R="$H/run.sh"; O="$1"
for mp in "none ALS" "A LoD2" "A ALS"; do set -- $mp; ( bash "$R" sight_${1}_$2 --cpus 2 --mem 12 mf3_sight.py $1 $2 2>&1 | grep -E "SIGHT|Error|Traceback|waiting" ) & sleep 90; done
wait
until [[ -f "$O/sight/none/LoD2.complete.json" ]] || ! docker ps --format '{{.Names}}' | grep -q sight_none_LoD2; do sleep 30; done
ls "$O"/sight/*/*.complete.json; echo "sight done $(date +%H:%M)"
[[ $(ls "$O"/sight/*/*.complete.json | wc -l) -eq 4 ]] || { echo "SIGHT INCOMPLETE"; exit 1; }
for p in LoD2 ALS; do bash "$R" judge_$p --cpus 4 --mem 30 mf4_judge.py $p none A 2>&1 | grep -E "CHECK|JUDGE|Error|error|Traceback"; done
echo CHAIN_A_DONE $(date +%H:%M)
