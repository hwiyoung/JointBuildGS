#!/usr/bin/env bash
# PHD-MAIN-BASE151-v1 LGDM: CPU job in jointbuildgs:dev; every input read-only, only OUT/lgdm read-write (nested mount).
#   bash run_lgdm_cpu.sh <tag> <cpus> <mem> <script.py> [args...]      container jbgs-b151-cpu-lgdm-<tag>
# Waits while host MemAvailable < 40 GB (GPU training and mesh jobs share the host). scientific_verdict: null
set -euo pipefail
W=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$W/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_base151_v1/PHD-MAIN-BASE151-v1"
EXP=$(realpath "$W/../JointBuildGS-exp")
tag=$1; cpus=$2; mem=$3; shift 3
mkdir -p "$OUT/lgdm/tmp/mpl" "$OUT/lgdm/logs"
while :; do
  avail=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)
  [ "$avail" -ge 40 ] && break
  echo "$(date '+%F %T') MemAvailable ${avail} GB < 40 GB: waiting" >&2
  sleep 120
done
echo "$(date '+%F %T') start jbgs-b151-cpu-lgdm-$tag MemAvailable ${avail} GB: $*" >&2
exec nice -n 15 docker run --rm --network none --name "jbgs-b151-cpu-lgdm-$tag" --user "$(id -u):$(id -g)" \
  --cpus "$cpus" --memory "$mem" --memory-swap "$mem" --oom-score-adj 800 --shm-size 2g \
  -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e TMPDIR=/b151/lgdm/tmp -e MPLCONFIGDIR=/b151/lgdm/tmp/mpl -e TZ=Asia/Seoul \
  -v "$W:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/b151:ro" -v "$OUT/lgdm:/b151/lgdm:rw" \
  -v "$EXP:/exp:ro" -w /repo/scripts/phd/main_base151_v1 --entrypoint python jointbuildgs:dev -B -u "$@"
