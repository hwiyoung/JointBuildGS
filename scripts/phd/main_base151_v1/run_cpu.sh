#!/usr/bin/env bash
# PHD-MAIN-BASE151-v1: CPU job in jointbuildgs:dev (inputs read-only, this task's payload and docs read-write).
#   bash run_cpu.sh <tag> <cpus> <mem> <script.py> [args...]
# scientific_verdict: null
set -euo pipefail
W=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$W/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_base151_v1/PHD-MAIN-BASE151-v1"
EXP=$(realpath "$W/../JointBuildGS-exp")
tag=$1; cpus=$2; mem=$3; shift 3
mkdir -p "$OUT/tmp" "$OUT/logs"
exec nice -n 15 docker run --rm --network none --name "jbgs-b151-cpu-$tag" --user "$(id -u):$(id -g)" \
  --cpus "$cpus" --memory "$mem" --memory-swap "$mem" --oom-score-adj 800 \
  -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e TMPDIR=/b151/tmp -e MPLCONFIGDIR=/b151/tmp/mpl -e TZ=Asia/Seoul \
  -v "$W:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/b151:rw" -v "$W/docs/experiments/phd/main_base151_v1:/repo/docs/experiments/phd/main_base151_v1:rw" \
  -v "$EXP:/exp:ro" -w /repo/scripts/phd/main_base151_v1 --entrypoint python jointbuildgs:dev -B -u "$@"
