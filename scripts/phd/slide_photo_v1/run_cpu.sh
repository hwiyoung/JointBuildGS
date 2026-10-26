#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
art=$(realpath "$repo/../JointBuildGS-artifacts")
pay="$art/phase-payloads/phd/slide_photo_v1/PHD-SLIDE-PHOTO-v1"
tag=$1; shift
docker image inspect jointbuildgs:dev --format '{{.Id}}' > "$pay/image_id.txt"
docker run --rm --name "jbgs-slide-photo-$tag" --network none --read-only \
  --user "$(id -u):$(id -g)" --cpus 16 --memory 24g --memory-swap 24g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e CUDA_VISIBLE_DEVICES= \
  -e NVIDIA_VISIBLE_DEVICES=void -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  -e MPLCONFIGDIR=/payload/tmp/mpl -e TMPDIR=/payload/tmp \
  -v "$repo:/repo:ro" -v "$art:/art:ro" -v "$pay:/payload" \
  -v "$repo/docs/experiments/phd/slide_photo_v1:/docs" \
  -v "$repo/configs/phd/slide_photo_v1:/cfg" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/slide_photo_v1 --entrypoint nice jointbuildgs:dev -n 19 python "$@" \
  2>&1 | tee "$pay/logs/$tag.log"
