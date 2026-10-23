#!/usr/bin/env bash
# PHD-MAIN-WIDEN0-v2: task-only writable mounts, no GPU, no network.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2"
DOCS="$REPO/docs/experiments/phd/main_widen0_v2"
CFG="$REPO/configs/phd/main_widen0_v2"
IMAGE=jointbuildgs:dev
tag=$1; shift
mkdir -p "$OUT/logs" "$OUT/tmp" "$DOCS" "$CFG"
log="$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
nice -n 19 docker run --rm --read-only --network none \
  --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --memory-swap 32g \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e CUDA_VISIBLE_DEVICES= -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache -e TZ=Asia/Seoul \
  -e WIDEN_COMMIT="$(git -C "$REPO" rev-parse HEAD)" \
  -e WIDEN_IMAGE_ID="$(docker image inspect -f '{{.Id}}' "$IMAGE")" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" \
  -v "$DOCS:/docs:rw" -v "$CFG:/cfg:rw" -w /out \
  -v /usr/share/fonts/opentype/noto:/fonts:ro \
  --entrypoint nice "$IMAGE" -n 19 python -B -u "/repo/scripts/phd/main_widen0_v2/$@" \
  2>&1 | tee "$log"
