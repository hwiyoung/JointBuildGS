#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1"
tag=$1; shift
docker run --rm --read-only --network none --runtime runc \
  --name "jbgs-finaltrain-$tag" --user "$(id -u):$(id -g)" \
  --cpus 8 --memory 40g --memory-swap 40g \
  -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e NUMPY_MADVISE_HUGEPAGE=0 \
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache -e TZ=Asia/Seoul \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" \
  -v "$REPO/configs/phd/main_finaltrain_v1:/cfg:rw" \
  -v "$REPO/docs/experiments/phd/main_finaltrain_v1:/docs:rw" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro -w /out \
  --entrypoint python jointbuildgs:dev -B -u \
  "/repo/scripts/phd/main_finaltrain_v1/$@"
