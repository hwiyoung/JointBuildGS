#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
art=$(realpath "$repo/../JointBuildGS-artifacts")
out="$art/phase-payloads/phd/main_regionview_v1/PHD-MAIN-REGIONVIEW-v1"
mkdir -p "$out/logs" "$out/tmp" "$out/holdout"
exec 9>"$out/task.lock"
flock -n 9
tag=$1; shift
nice -n 19 docker run --rm --read-only --network none --runtime runc \
  --name "jbgs-regionview-$tag" --user "$(id -u):$(id -g)" --cpus 2 --memory 8g --memory-swap 8g \
  -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache -e TZ=Asia/Seoul \
  -e REGIONVIEW_COMMIT="$(GIT_OPTIONAL_LOCKS=0 git -C "$repo" rev-parse HEAD)" \
  -e REGIONVIEW_IMAGE="$(docker image inspect -f '{{.Id}}' jointbuildgs:dev)" \
  -v "$repo:/repo:ro" -v "$art:/art:ro" -v "$out:/out:rw" \
  -v "$repo/configs/phd/main_regionview_v1:/cfg:rw" \
  -v "$repo/docs/experiments/phd/main_regionview_v1:/docs:rw" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro -w /out \
  --entrypoint nice jointbuildgs:dev -n 19 python -B -u \
  "/repo/scripts/phd/main_regionview_v1/$@" \
  2>&1 | tee "$out/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
