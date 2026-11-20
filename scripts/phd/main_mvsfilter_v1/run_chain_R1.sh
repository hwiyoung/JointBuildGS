#!/usr/bin/env bash
# 회신 1 사슬: A2 문턱 넷 셈(+1 % 판 바이트 같음 확인, c = 1 화소 나눔) → 원통 막대그림(c = 1 나눔·깊이) → 줄인 판의 원통 값(MF_CYL_ONLY)·패치마다 c 값 → 표.
# run_chain_N2 와 함께 돌므로 공용 칸 여유를 보고 시작. 실행기는 run2.sh(환경 값 전달).
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); R="$H/run2.sh"; O="$1"
SL=/sys/fs/cgroup/docker.slice/docker-workloads.slice
st() { echo "$1 $(date +%H:%M)"; }
room() { while (( $(cat $SL/memory.current) + $1*1024*1024*1024 > $(cat $SL/memory.high) )); do sleep 120; done; }
TILES_BIG="6909_53361 6909_53359 6908_53359 6908_53360 6910_53361 6909_53360 6910_53360 6908_53361 6909_53362 6910_53362 6910_53359 6911_53362 6910_53363 6909_53358 6909_53363 6911_53361 6908_53362 6908_53358 6907_53359 6911_53360 6907_53360 6910_53358 6911_53363 6912_53362"
room 14; bash "$R" a2tol --cpus 32 --mem 24 mf15_a2tol.py count 2>&1 | grep -E "TOL|DIAG|Error|Traceback|assert" | cut -c1-400; st "count"
room 26; bash "$R" a2hist --cpus 8 --mem 24 mf15_a2tol.py hist $TILES_BIG 2>&1 | grep -E "Error|Traceback|assert" | head; st "hist $(ls $O/a2tol/hist/*.npz | wc -l)"
for tag in 0p5 0p2 0p1; do
  room 12; MF_CYL_ONLY=1 bash "$R" patch_A2d$tag --cpus 40 --mem 30 mf2_patch.py A2d$tag $TILES_BIG 2>&1 | grep -E "Error|Traceback" | head -3; st "cyl A2d$tag $(ls $O/patch/A2d$tag/*.npz | wc -l)"
  room 18; MF_A2DIR=a2tol/t$tag MF_A2OUT=a2_patch_t$tag bash "$R" a2patch_$tag --cpus 8 --mem 16 mf13_A2_patch.py $TILES_BIG 2>&1 | grep -E "Error|Traceback|assert" | head -3; st "a2 patch t$tag $(ls $O/a2_patch_t$tag/*.json | wc -l)"
done
bash "$R" a2tol_table --cpus 2 --mem 16 mf15_a2tol.py table 2>&1 | grep -E "Error|Traceback|\|" | head -12
echo CHAIN_R1_DONE $(date +%H:%M)
