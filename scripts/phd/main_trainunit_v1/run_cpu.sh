#!/usr/bin/env bash
# CPU container for TRAINUNIT preparation/scoring steps: inputs read-only, writes only /tu and this task's docs.
#   bash run_cpu.sh <tag> <cpus> <memory> <script.py> [args...]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts
TU="$ART/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1"
tag=$1; cpus=$2; mem=$3; shift 3
mkdir -p "$TU/tmp" "$TU/logs"
nice -n 10 docker run --rm --read-only --network none --runtime runc \
  --name "jbgs-trainunit-$tag" --user "$(id -u):$(id -g)" --cpus "$cpus" --memory "$mem" --memory-swap "$mem" \
  -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e NUMPY_MADVISE_HUGEPAGE=0 \
  -e TMPDIR=/tu/tmp -e MPLCONFIGDIR=/tu/tmp/mpl -e XDG_CACHE_HOME=/tu/tmp/cache -e TZ=Asia/Seoul \
  -v "$REPO:/repo:ro" -v "$REPO/docs/experiments/phd/main_trainunit_v1:/repo/docs/experiments/phd/main_trainunit_v1:rw" \
  -v "$ART:/art:ro" -v "$ART:/artifacts/JointBuildGS:ro" -v "$TU:/tu:rw" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro -w /tu --entrypoint python jointbuildgs:dev -B -u \
  "/repo/scripts/phd/main_trainunit_v1/$@" 2>&1 | tee "$TU/logs/$tag.log"
