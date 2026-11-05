#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PAY="$ART/phase-payloads/phd"
OUT="$PAY/pres_realbldg_v1/PHD-PRES-REALBLDG-v1"
mkdir -p "$OUT/tmp" "$OUT/logs"
tag=$1; shift
nice -n 19 docker run --rm --read-only --network none --runtime runc \
 --name "jbgs-pres-realbldg-$tag" --user "$(id -u):$(id -g)" --cpus 8 --memory 32g --memory-swap 32g \
 -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
 -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e NUMPY_MADVISE_HUGEPAGE=0 \
 -e TMPDIR=/pres/tmp -e MPLCONFIGDIR=/pres/tmp/mpl -e XDG_CACHE_HOME=/pres/tmp/cache -e TZ=Asia/Seoul \
 -e PRES_COMMIT="$(git -C "$REPO" rev-parse HEAD)" \
 -e PRES_IMAGE="$(docker image inspect -f '{{.Id}}' jointbuildgs:dev)" \
 -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$ART:/artifacts/JointBuildGS:ro" \
 -v "$PAY/main_rescore_v1/PHD-MAIN-RESCORE-v1:/out:ro" -v "$PAY:/ph:ro" \
 -v "$OUT:/pres:rw" -v "$REPO/configs/phd/pres_realbldg_v1:/cfg:rw" \
 -v "$REPO/docs/experiments/phd/pres_realbldg_v1:/docs:rw" \
 -v /usr/share/fonts/opentype/noto:/fonts:ro -w /pres --entrypoint nice jointbuildgs:dev -n 19 python -B -u \
 "/repo/scripts/phd/pres_realbldg_v1/$@" 2>&1 | tee "$OUT/logs/$tag.log"
