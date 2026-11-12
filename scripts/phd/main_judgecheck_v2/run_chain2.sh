#!/usr/bin/env bash
# 광도 점수와 본값 판정: 사진 준비 끝 → 빈 GPU 가 있으면 GPU 로 구역 차례로, 두 GPU 가 30분 넘게 차 있으면 CPU 로 (구역 넷씩) → s5_judge base
set -uo pipefail
cd "$(dirname "$0")/../../.."
ART=$(realpath ../JointBuildGS-artifacts); OUT=$ART/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2
memwait(){ while (( $(free | awk 'NR==2{print int($3*100/$2)}') > ${1:-78} )); do sleep 30; done; }
until grep -q PREP_DONE $OUT/logs/chain1b.out; do sleep 30; done
tiles=$(ls $OUT/photo_prepared/*.npz | xargs -n1 basename | sed 's/.npz//')
start=$(cat $OUT/logs/gpu_wait_start.txt)
free_gpu(){ for g in 0 1; do u=$(nvidia-smi -i $g --query-compute-apps=pid --format=csv,noheader | wc -l); [[ $u -eq 0 ]] && { echo $g; return; }; done; echo none; }
for t in $tiles; do
  [[ -f $OUT/photo_scores/$t/complete.json ]] && continue
  g=$(free_gpu)
  while [[ $g == none ]] && (( $(date +%s) - start < 1800 )); do sleep 60; g=$(free_gpu); done
  if [[ $g != none ]]; then
    echo "SCORE_GPU $t gpu$g $(date +%H:%M)"; memwait
    bash scripts/phd/main_judgecheck_v2/run.sh score_$t --cpus 4 --mem 24 --gpu $g s3_score.py cuda $t > /dev/null 2>&1 || echo "SCORE_FAIL $t"
  else
    echo "SCORE_CPU_MODE from $t $(date +%H:%M) (both GPUs busy > 30 min)"; break
  fi
done
left=$(for t in $tiles; do [[ -f $OUT/photo_scores/$t/complete.json ]] || echo $t; done)
for t in $left; do
  while (( $(jobs -rp | wc -l) >= 4 )); do sleep 15; done; memwait
  ( bash scripts/phd/main_judgecheck_v2/run.sh score_cpu_$t --cpus 4 --mem 16 s3_score.py cpu $t > /dev/null 2>&1 || echo "SCORE_FAIL $t"; echo "SCORE_CPU_TILE $t $(date +%H:%M)" ) &
  sleep 5
done
wait
echo "SCORES_DONE $(date +%H:%M)"
until grep -q "SIGHT_LoD2_EXIT" $OUT/logs/chain1b.out && grep -q "SIGHT_ALS_EXIT" $OUT/logs/chain1b.out; do sleep 30; done
bash scripts/phd/main_judgecheck_v2/run.sh judge_base --cpus 4 --mem 32 s5_judge.py base > /dev/null 2>&1 && echo "JUDGE_BASE_OK $(date +%H:%M)" || echo "JUDGE_BASE_FAIL"
