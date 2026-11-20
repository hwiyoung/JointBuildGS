#!/usr/bin/env bash
# 묶음 나 사슬 뒷부분(11-20 17:5x, 사용자 결정 "둘씩 돌리기"): run_chain_B.sh 의 가시성 단계를 둘씩으로 바꿈.
# 가시성은 동시에 둘까지, 공용 묶음(docker-workloads.slice) 여유가 16 GiB 넘을 때만 새로 시작(한 작업 12 GB + 3 GiB).
# C 가시성은 C 패치 값(22구역)이 끝난 뒤. 그다음 판정·표·점검은 run_chain_B.sh 와 같음. 설정·결과 값은 바꾸지 않음.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); R="$H/run.sh"; O="$1"
SL=/sys/fs/cgroup/docker.slice/docker-workloads.slice
st() { echo "$1 $(date +%H:%M)"; }
free_gib() { echo $(( ($(cat $SL/memory.high) - $(cat $SL/memory.current)) / 1024/1024/1024 )); }
patch_done() { [[ $(ls "$O"/patch/$1/*.npz 2>/dev/null | wc -l) -eq 22 ]] && ! docker ps --format '{{.Names}}' | grep -qx "jbgs-mvsfilter1-patch_$1"; }
JOBS=(B_orig:ALS B_orig:LoD2 B_view:ALS B_view:LoD2 C:ALS C:LoD2)
declare -A PID=()
for j in "${JOBS[@]}"; do
  m=${j%%:*}; p=${j##*:}
  [[ -f "$O/sight/$m/$p.complete.json" ]] && { st "sight $m $p already"; continue; }
  until patch_done "$m"; do sleep 120; done
  while :; do
    n=0; for k in "${!PID[@]}"; do kill -0 "${PID[$k]}" 2>/dev/null && n=$((n+1)); done
    (( n < 2 && $(free_gib) >= 16 )) && break; sleep 120
  done
  st "sight $m $p start (slice free $(free_gib) GiB)"
  ( bash "$R" sight_${m}_$p --cpus 2 --mem 12 mf3_sight.py $m $p 2>&1 | grep -E "SIGHT|Error|Traceback"; st "sight $m $p end" ) &
  PID[$j]=$!; sleep 300   # 앞 작업의 메모리가 다 오른 뒤에 여유를 다시 봄
done
wait
[[ $(ls "$O"/sight/*/*.complete.json | wc -l) -eq 10 ]] || { echo "SIGHT INCOMPLETE"; exit 1; }; st "sight done"
for p in LoD2 ALS; do bash "$R" judge_$p --cpus 4 --mem 30 mf4_judge.py $p none A B_orig B_view C 2>&1 | grep -E "CHECK|JUDGE|Error|error|Traceback"; done
bash "$R" tables_B --cpus 8 --mem 24 mf7_tables.py A B_orig B_view C 2>&1 | grep -E "Error|Traceback"
bash "$R" checks_B --cpus 4 --mem 16 mf7b_checks.py A B_orig B_view C 2>&1 | grep -E "CHECK|Error|Traceback" | cut -c1-300
echo CHAIN_B_DONE $(date +%H:%M)
