#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PAY="$ART/phase-payloads/phd"
OUT="$PAY/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1"
mkdir -p "$OUT/tmp" "$OUT/logs"
tag=$1
shift
nice -n 19 docker run --rm --read-only --network none --runtime runc \
 --name "jbgs-gtjudge-$tag" --user "$(id -u):$(id -g)" --cpus 6 --memory 32g --memory-swap 32g \
 -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
 -e TMPDIR=/gtjudge/tmp -e MPLCONFIGDIR=/gtjudge/tmp/mpl -e XDG_CACHE_HOME=/gtjudge/tmp/cache -e TZ=Asia/Seoul \
 -e GTJUDGE_COMMIT="$(git -C "$REPO" rev-parse HEAD)" \
 -e GTJUDGE_IMAGE="$(docker image inspect -f '{{.Id}}' jointbuildgs:dev)" \
 -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$ART:/artifacts/JointBuildGS:ro" -v "$PAY:/ph:ro" \
 -v "$PAY/main_rescore_v1/PHD-MAIN-RESCORE-v1:/out:ro" \
 -v "$PAY/main_release_v1/PHD-MAIN-RELEASE-v1:/release:ro" -v "$OUT:/gtjudge:rw" \
 -v "$REPO/configs/phd/main_gtjudge_v1:/cfg:rw" -v "$REPO/docs/experiments/phd/main_gtjudge_v1:/docs:rw" \
 -v /usr/share/fonts/opentype/noto:/fonts:ro -w /gtjudge --entrypoint nice jointbuildgs:dev -n 19 python -B -u \
 "/repo/scripts/phd/main_gtjudge_v1/$@" 2>&1 | tee "$OUT/logs/$tag.log"
