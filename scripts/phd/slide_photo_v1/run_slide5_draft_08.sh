#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../../.." && pwd)
art=$(realpath "$repo/../JointBuildGS-artifacts")
pay="$art/phase-payloads/phd/slide_photo_v1/PHD-SLIDE-PHOTO-v1"
out="$repo/docs/experiments/phd/slide_photo_v1/revision_08"
cache="$pay/revision_08"
mkdir -p "$out" "$cache"
docker image inspect jointbuildgs:dev --format '{{.Id}}' > "$out/docker_image_id.txt"
docker run --rm --name jbgs-slide5-draft-r8 --network none --read-only \
  --user "$(id -u):$(id -g)" --cpus 2 --memory 4g --memory-swap 4g \
  --tmpfs /tmp:rw,nosuid,nodev,size=512m \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MPLCONFIGDIR=/tmp/mpl \
  -e "TASK_BASE_COMMIT=$(git -C "$repo" rev-parse HEAD)" \
  -v "$repo:/repo:ro" -v "$art:/art:ro" -v "$pay:/payload:ro" \
  -v "$cache:/payload/revision_08" \
  -v "$repo/docs/experiments/phd/slide_photo_v1:/docs:ro" -v "$out:/docs/revision_08" \
  -v "$repo/configs/phd/slide_photo_v1:/cfg:ro" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/slide_photo_v1 --entrypoint nice jointbuildgs:dev \
  -n 19 python slide5_draft_revision_08.py "$@" 2>&1 | tee "$cache/run.log"
