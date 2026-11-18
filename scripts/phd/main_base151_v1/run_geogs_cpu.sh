#!/usr/bin/env bash
# PHD-MAIN-BASE151-v1: GeoGS preprocessing job (jointbuildgs:geogs-official-db40c95-rtree-v1-b151, CPU, /opt/geogs/bin/python).
#   bash run_geogs_cpu.sh <tag> <cpus> <mem> b151_geogs_inputs.py <args...>
# scientific_verdict: null
set -euo pipefail
W=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$W/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_base151_v1/PHD-MAIN-BASE151-v1"
EXP=$(realpath "$W/../JointBuildGS-exp")
SRC="$ART/phase-payloads/phd/main_fix_v1/PHD-MAIN-FIX-v1/geogs/source/GeoGS-official-adapters-v1-fix1"
tag=$1; cpus=$2; mem=$3; shift 3
exec nice -n 15 docker run --rm --network none --name "jbgs-b151-cpu-$tag" --user "$(id -u):$(id -g)" \
  --cpus "$cpus" --memory "$mem" --memory-swap "$mem" --shm-size 4g --oom-score-adj 800 \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS=2 -e TZ=Asia/Seoul \
  -v "$SRC:/source:ro" -v "$W:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/b151:rw" -v "$EXP:/exp:ro" \
  -w /repo/scripts/phd/main_base151_v1 --entrypoint /opt/geogs/bin/python jointbuildgs:geogs-official-db40c95-rtree-v1-b151 -B -u "$@"
