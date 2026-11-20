#!/usr/bin/env bash
# 묶음 나2 사슬(덧붙임 1): A2 패치 값 → 가시성 둘(함께, 공용 칸 여유 16 GiB 일 때) → A2_rm(점검 2) → 상자 A2 → 판정·채점(여섯 줄) → 표·점검 → 점검 판·곡선·AUC → 그림.
# 함께: A2 패치 값이 도는 동안 패치마다 c 값(mf13, 가벼움).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); R="$H/run.sh"; O="$1"
SL=/sys/fs/cgroup/docker.slice/docker-workloads.slice
st() { echo "$1 $(date +%H:%M)"; }
room() { while (( $(cat $SL/memory.current) + $1*1024*1024*1024 > $(cat $SL/memory.high) )); do sleep 120; done; }
TILES_BIG="6909_53361 6909_53359 6908_53359 6908_53360 6910_53361 6909_53360 6910_53360 6908_53361 6909_53362 6910_53362 6910_53359 6911_53362 6910_53363 6909_53358 6909_53363 6911_53361 6908_53362 6908_53358 6907_53359 6911_53360 6907_53360 6910_53358 6911_53363 6912_53362"
( room 18; bash "$R" a2patch --cpus 8 --mem 16 mf13_A2_patch.py $TILES_BIG 2>&1 | grep -E "Error|Traceback|assert" | head -5; st "a2 patch stats $(ls $O/a2_patch/*.json | wc -l)" ) &
P1=$!
room 12; bash "$R" patch_A2 --cpus 40 --mem 30 mf2_patch.py A2 $TILES_BIG 2>&1 | grep -E "Error|Traceback" | head -5; st "patch A2 $(ls $O/patch/A2/*.npz | wc -l)"
for p in ALS LoD2; do room 16; ( bash "$R" sight_A2_$p --cpus 2 --mem 12 mf3_sight.py A2 $p 2>&1 | grep -E "SIGHT|Error|Traceback"; st "sight A2 $p" ) & sleep 300; done
wait
room 12; bash "$R" patch_A2_rm --cpus 40 --mem 30 mf2_patch.py A2_rm $TILES_BIG 2>&1 | grep -E "Error|Traceback" | head -5; st "rm A2 $(ls $O/patch/A2_rm/*.npz | wc -l)"
room 14; bash "$R" box_A2 --cpus 16 --mem 30 mf10c_box_a2.py B0_b10 B173nb_b10 R1rep_b10 2>&1 | grep -E "A2BOX|BOXA2|Error|Traceback" | cut -c1-500; st "box A2"
[[ $(ls "$O"/sight/A2/*.complete.json | wc -l) -eq 2 ]] || { echo "SIGHT A2 INCOMPLETE"; exit 1; }
for p in LoD2 ALS; do bash "$R" judge2_$p --cpus 4 --mem 30 mf4_judge.py $p none A A2 B_orig B_view C 2>&1 | grep -E "CHECK|JUDGE|Error|error|Traceback" | cut -c1-300; done
bash "$R" tables_N2 --cpus 8 --mem 24 mf7_tables.py A A2 B_orig B_view C 2>&1 | grep -E "Error|Traceback"
bash "$R" checks_N2 --cpus 4 --mem 16 mf7b_checks.py A A2 B_orig B_view C 2>&1 | grep -E "CHECK|Error|Traceback" | cut -c1-300
bash "$R" checkmode --cpus 4 --mem 24 mf11_check.py A A2 B_orig B_view C 2>&1 | grep -E "CHECK|Error|Traceback" | cut -c1-300; st "checkmode"
for p in LoD2 ALS; do bash "$R" figs_A2_$p --cpus 4 --mem 24 mf8_figs.py $p A2 2>&1 | grep -E "Error|Traceback" | head -5; st "figs A2 $p"; done
echo CHAIN_N2_DONE $(date +%H:%M)
