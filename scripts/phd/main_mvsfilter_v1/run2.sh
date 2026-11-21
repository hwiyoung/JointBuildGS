#!/usr/bin/env bash
# (run.sh 복사본 + 회신 1 환경 값 MF_CYL_ONLY·MF_A2DIR·MF_A2OUT 전달; run.sh 는 도는 사슬이 쓰는 중이라 고치지 않음)
# PHD-MAIN-MVSFILTER-v1 실행기 (JUDGESTRUCT-v1 run.sh 옮김, CPU만): run.sh <tag> [--cpus N] [--mem G] <script.py> [args]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_mvsfilter_v1/PHD-MAIN-MVSFILTER-v1"
CFG="$REPO/configs/phd/main_mvsfilter_v1"
DOC="$REPO/docs/experiments/phd/main_mvsfilter_v1"
mkdir -p "$OUT/tmp" "$OUT/logs"
tag=$1; shift
cpus=4; mem=32; image=jointbuildgs:dev
while [[ "$1" == --* ]]; do
  case "$1" in --cpus) cpus=$2; shift 2;; --mem) mem=$2; shift 2;; *) echo "bad opt $1"; exit 2;; esac
done
(( mem <= 32 )) || { echo "memory > 32 GB refused"; exit 2; }
while (( $(free | awk '/^Mem|^메모리/{printf "%d", ($3)*100/$2}') > 80 )); do echo "host memory > 80 %, waiting"; sleep 60; done
SL=/sys/fs/cgroup/docker.slice/docker-workloads.slice   # 공용 묶음의 memory.high(60 GiB)에 닿으면 모든 컨테이너가 조여짐 → 3 GiB 남을 때만 시작
if [[ -r $SL/memory.high && $(cat $SL/memory.high) != max ]]; then
  while (( $(cat $SL/memory.current) + 3*1024*1024*1024 > $(cat $SL/memory.high) )); do echo "docker-workloads slice near memory.high, waiting"; sleep 120; done
fi
nice -n 19 docker run --rm --read-only --network none --runtime runc -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void \
  --name "jbgs-mvsfilter1-$tag" --user "$(id -u):$(id -g)" \
  --cpus "$cpus" --memory "${mem}g" --memory-swap "${mem}g" --shm-size 2g --tmpfs /fast:rw,exec,size=8g \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e NUMPY_MADVISE_HUGEPAGE=0 \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e JC2_CPUS="$cpus" -e MF_CPUS="$cpus" -e MF_RING_REPRO="${MF_RING_REPRO:-1}" -e MF_CYL_ONLY="${MF_CYL_ONLY:-0}" -e MF_A2DIR="${MF_A2DIR:-a2}" -e MF_A2OUT="${MF_A2OUT:-a2_patch}" -e MF_MAPS_ONLY="${MF_MAPS_ONLY:-0}" \
  -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache -e TZ=Asia/Seoul \
  -e MF_COMMIT="$(GIT_OPTIONAL_LOCKS=0 git -C "$REPO" rev-parse HEAD)" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" -v "$CFG:/cfg:ro" -v "$DOC:/docs:rw" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro -w /out \
  --entrypoint nice $image -n 19 python -B -u \
  "/repo/scripts/phd/main_mvsfilter_v1/$@" \
  2>&1 | tee "$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
