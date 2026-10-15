#!/usr/bin/env bash
# PHD-CH6-SUPPORT-v1: everything after batch A (host driver; every step in Docker through run_queue.sh).
#   B1 labels of the seven ranges -> t4_offset.py and a first t5_judge.py (ranges + boxes; supplements absent)
#   B2 B173_b0 own values, box and range mask-off runs -> B173_b0 labels -> t5_judge.py (full) -> t5_figs.py
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); S="$REPO/scripts/phd/ch6_support_v1"
P="$(realpath "$REPO/../JointBuildGS-artifacts")/phase-payloads/phd/ch6_support_v1/PHD-CH6-SUPPORT-v1"; J="$P/jobs"
note() { echo "- $(date '+%m-%d %H:%M:%S') $*" >> "$P/progress.md"; }
note "B1 시작: 일곱 범위 라벨 7건"; bash "$S/run_queue.sh" "$J/b1_labels.txt" 2 10 14; note "B1 끝"
WORKDIR=scripts/phd/ch6_support_v1 bash "$S/run_queue.sh" "$J/c_t4.txt" 1 8 12; note "일 4 집계 끝(t4_offset.py)"
WORKDIR=scripts/phd/ch6_support_v1 bash "$S/run_queue.sh" "$J/c_t5.txt" 1 8 12; note "일 5 첫 집계 끝(보충 없이)"
touch "$P/jobs/first_results.done"
note "B2 시작: B173만 자체 값 2건, 상자 마스크 끔 6건, 범위 마스크 끔 14건"; bash "$S/run_queue.sh" "$J/b2_rest.txt" 2 10 14; note "B2 끝"
bash "$S/run_queue.sh" "$J/b_self_gt.txt" 1 10 14; note "B173만 자체 값 라벨 끝"
WORKDIR=scripts/phd/ch6_support_v1 bash "$S/run_queue.sh" "$J/c_t5.txt" 1 8 12; note "일 5 전체 집계 끝"
WORKDIR=scripts/phd/ch6_support_v1 bash "$S/run_queue.sh" "$J/c_t5figs.txt" 1 8 12; note "일 5 그림 끝"
touch "$P/jobs/all.done"
