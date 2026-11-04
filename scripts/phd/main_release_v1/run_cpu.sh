#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PAY="$ART/phase-payloads/phd"
OUT="$PAY/main_release_v1/PHD-MAIN-RELEASE-v1"
tag=$1; shift
nice -n 19 docker run --rm --read-only --network none --runtime runc \
 --name "jbgs-release-$tag" --user "$(id -u):$(id -g)" --cpus 6 --memory 32g --memory-swap 32g \
 -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e NUMPY_MADVISE_HUGEPAGE=0 \
 -e TMPDIR=/release/tmp -e MPLCONFIGDIR=/release/tmp/mpl -e XDG_CACHE_HOME=/release/tmp/cache -e TZ=Asia/Seoul \
 -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$ART:/artifacts/JointBuildGS:ro" -v "$PAY:/ph:ro" \
 -v "$PAY/main_rescore_v1/PHD-MAIN-RESCORE-v1:/out:ro" -v "$OUT:/release:rw" \
 -v "$REPO/configs/phd/main_release_v1:/cfg:rw" -v "$REPO/docs/experiments/phd/main_release_v1:/docs:rw" \
 -v /usr/share/fonts/opentype/noto:/fonts:ro -w /release --entrypoint nice jointbuildgs:dev -n 19 python -B -u \
 "/repo/scripts/phd/main_release_v1/$@" 2>&1 | tee "$OUT/logs/$tag.log"
