#!/usr/bin/env bash
# PHD-MAIN-JUDGEABL-v1 실행기 (JUDGECHECK-v2 run.sh 옮김, CPU만): run.sh <tag> [--cpus N] [--mem G] <script.py> [args]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_judgeabl_v1/PHD-MAIN-JUDGEABL-v1"
CFG="$REPO/configs/phd/main_judgeabl_v1"
DOC="$REPO/docs/experiments/phd/main_judgeabl_v1"
mkdir -p "$OUT/tmp" "$OUT/logs"
tag=$1; shift
cpus=4; mem=32; image=jointbuildgs:dev
while [[ "$1" == --* ]]; do
  case "$1" in --cpus) cpus=$2; shift 2;; --mem) mem=$2; shift 2;; *) echo "bad opt $1"; exit 2;; esac
done
(( mem <= 32 )) || { echo "memory > 32 GB refused"; exit 2; }
# 컴퓨터 메모리 사용 80 % 넘으면 기다림
while (( $(free | awk '/^Mem|^메모리/{printf "%d", ($3)*100/$2}') > 80 )); do echo "host memory > 80 %, waiting"; sleep 60; done
nice -n 19 docker run --rm --read-only --network none --runtime runc -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void \
  --name "jbgs-judgeabl1-$tag" --user "$(id -u):$(id -g)" \
  --cpus "$cpus" --memory "${mem}g" --memory-swap "${mem}g" --shm-size 2g \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e NUMPY_MADVISE_HUGEPAGE=0 \
  -e OMP_NUM_THREADS=$cpus -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e JP_CPUS="$cpus" \
  -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache -e TZ=Asia/Seoul \
  -e JP_COMMIT="$(GIT_OPTIONAL_LOCKS=0 git -C "$REPO" rev-parse HEAD)" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" -v "$CFG:/cfg:ro" -v "$DOC:/docs:rw" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro -w /out \
  --entrypoint nice $image -n 19 python -B -u \
  "/repo/scripts/phd/main_judgeabl_v1/$@" \
  2>&1 | tee "$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
