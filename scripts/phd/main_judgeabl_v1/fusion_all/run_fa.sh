#!/usr/bin/env bash
# PHD-MAIN-JUDGEABL-v1 5절 실행기 (CPU만, jointbuildgs:dev): run_fa.sh <tag> [--cpus N] [--mem G] <script.py> [args]
# 다른 작업 결과는 읽기만(ro). 쓰는 곳 = /res (PH/main_judgeabl_v1/PHD-MAIN-JUDGEABL-v1/fusion_all).
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
RES="$PH/main_judgeabl_v1/PHD-MAIN-JUDGEABL-v1/fusion_all"
S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"; S1="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"
DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; PREP="$PH/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
CFG="$REPO/configs/phd/main_judgeabl_v1"; DOC="$REPO/docs/experiments/phd/main_judgeabl_v1"
mkdir -p "$RES/tmp" "$RES/logs"
tag=$1; shift
cpus=16; mem=32
while [[ "$1" == --* ]]; do
  case "$1" in --cpus) cpus=$2; shift 2;; --mem) mem=$2; shift 2;; *) echo "bad opt $1"; exit 2;; esac
done
(( mem <= 32 )) || { echo "memory > 32 GB refused"; exit 2; }
while (( $(free | awk '/^Mem|^메모리/{printf "%d", ($3)*100/$2}') > 80 )); do echo "host memory > 80 %, waiting"; sleep 60; done
nice -n 19 docker run --rm --network none -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void \
  --name "jbgs-judgeabl1-fa-$tag" --user "$(id -u):$(id -g)" \
  --cpus "$cpus" --memory "${mem}g" --memory-swap "${mem}g" --shm-size 4g \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -e FA_CFG="${FA_CFG:-judgeabl_v1_fusion_all.json}" -e TMPDIR=/res/tmp -e MPLCONFIGDIR=/res/tmp/mpl -e TZ=Asia/Seoul \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$PH:/ph:ro" -v "$RES:/res:rw" -v "$S0:/s0:ro" -v "$S1:/out:ro" -v "$DR:/dr:ro" -v "$PREP:/prep:ro" \
  -v "$CFG:/cfg:ro" -v "$DOC:/docs:rw" -w /repo/scripts/phd/main_judgeabl_v1/fusion_all \
  --entrypoint nice jointbuildgs:dev -n 19 python -B -u "$@" \
  2>&1 | tee "$RES/logs/${tag}_$(date +%Y%m%dT%H%M%S).log"
