#!/usr/bin/env bash
# PHD-MAIN-JUDGECHECK-v2 실행기: run.sh <tag> [--cpus N] [--mem G] [--gpu I] <script.py> [args]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_judgecheck_v2/PHD-MAIN-JUDGECHECK-v2"
CFG="$REPO/configs/phd/main_judgecheck_v2"
DOC="$REPO/docs/experiments/phd/main_judgecheck_v2"
mkdir -p "$OUT/tmp" "$OUT/logs"
tag=$1; shift
cpus=4; mem=32; gpu=""; image=jointbuildgs:dev
while [[ "$1" == --* ]]; do
  case "$1" in --cpus) cpus=$2; shift 2;; --mem) mem=$2; shift 2;; --gpu) gpu=$2; shift 2;; --image) image=$2; shift 2;; *) echo "bad opt $1"; exit 2;; esac
done
(( mem <= 32 )) || { echo "memory > 32 GB refused"; exit 2; }
runtime=(--runtime runc -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void)
if [[ -n "$gpu" ]]; then runtime=(--runtime nvidia --gpus device=$gpu -e NVIDIA_VISIBLE_DEVICES=$gpu); fi
nice -n 19 docker run --rm --read-only --network none "${runtime[@]}" \
  --name "jbgs-judgecheck2-$tag" --user "$(id -u):$(id -g)" \
  --cpus "$cpus" --memory "${mem}g" --memory-swap "${mem}g" --shm-size 2g \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e NUMPY_MADVISE_HUGEPAGE=0 \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e JC2_CPUS="$cpus" \
  -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache -e TZ=Asia/Seoul \
  -e JC2_COMMIT="$(GIT_OPTIONAL_LOCKS=0 git -C "$REPO" rev-parse HEAD)" \
  -e JC2_IMAGE="$(docker image inspect -f "{{.Id}}" $image)" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" -v "$CFG:/cfg:rw" -v "$DOC:/docs:rw" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro -w /out \
  --entrypoint nice $image -n 19 python -B -u \
  "/repo/scripts/phd/main_judgecheck_v2/$@" \
  2>&1 | tee "$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
