#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_wallphoto_v1/PHD-MAIN-WALLPHOTO-v1"
docker run -d --restart on-failure:3 --read-only --network none --name jbgs-wallphoto-worker \
 --user "$(id -u):$(id -g)" --cpus 8 --memory 12g --memory-swap 12g \
 -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS=8 \
 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e TZ=Asia/Seoul \
 -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache \
 -e PHOTOCHECK_RAM_CACHE_BYTES=2147483648 --tmpfs /out/tmp/image_cache_ram:rw,size=3g,mode=1777 \
 -e PHOTOCHECK_COMMIT="$(git -C "$REPO" rev-parse HEAD)" \
 -e PHOTOCHECK_IMAGE="$(docker image inspect -f '{{.Id}}' jointbuildgs:dev)" \
 -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" \
 -v "$REPO/docs/experiments/phd/main_wallphoto_v1:/docs:rw" \
 -v "$REPO/configs/phd/main_wallphoto_v1:/cfg:rw" -v /usr/share/fonts/opentype/noto:/fonts:ro \
 -w /out --entrypoint nice jointbuildgs:dev -n 19 python -B -u \
 /repo/scripts/phd/main_wallphoto_v1/admit_worker.py
