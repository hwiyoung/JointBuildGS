#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1"
CFG="$REPO/configs/phd/main_rescore_v1"
DOC="$REPO/docs/experiments/phd/main_rescore_v1"
mkdir -p "$OUT/tmp" "$OUT/logs"
tag=$1; shift
nice -n 19 docker run --rm --read-only --network none --runtime runc \
 --name "jbgs-rescore-$tag" --user "$(id -u):$(id -g)" --cpus 4 --memory 32g --memory-swap 32g \
 -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
 -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e NUMPY_MADVISE_HUGEPAGE=0 \
 -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache -e TZ=Asia/Seoul \
 -e RESCORE_COMMIT="$(GIT_OPTIONAL_LOCKS=0 git -C "$REPO" rev-parse HEAD)" \
 -e RESCORE_IMAGE="$(docker image inspect -f '{{.Id}}' jointbuildgs:dev)" \
 -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$ART/phase-payloads/phd:/ph:ro" \
 -v "$OUT:/out:rw" -v "$CFG:/cfg:rw" -v "$DOC:/docs:rw" -v /usr/share/fonts/opentype/noto:/fonts:ro \
 -w /out --entrypoint nice jointbuildgs:dev -n 19 python -B -u \
 "/repo/scripts/phd/main_rescore_v1/$@" 2>&1 | tee "$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
