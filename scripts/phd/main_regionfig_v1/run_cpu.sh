#!/usr/bin/env bash
# PHD-MAIN-REGIONFIG-v1: isolated CPU process, <=7.5 GB, task-only writes.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PAY="$ART/phase-payloads/phd/main_regionfig_v1/PHD-MAIN-REGIONFIG-v1"
DOC="$REPO/docs/experiments/phd/main_regionfig_v1"
CFG="$REPO/configs/phd/main_regionfig_v1"
tag=$1; shift
stamp=$(date -u +%Y%m%dT%H%M%SZ)
docker image inspect jointbuildgs:dev --format '{{.Id}}' > "$PAY/image_id.txt"
set +e
docker run --rm --name "jbgs-regionfig-$tag" --network none --read-only \
  --user "$(id -u):$(id -g)" --cpus 4 --memory 7500000000 --memory-swap 7500000000 \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e CUDA_VISIBLE_DEVICES= \
  -e NVIDIA_VISIBLE_DEVICES=void -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 \
  -e MPLCONFIGDIR=/payload/cache/mpl -e XDG_CACHE_HOME=/payload/cache -e TMPDIR=/payload/tmp \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$PAY:/payload" -v "$DOC:/docs" -v "$CFG:/cfg" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/main_regionfig_v1 --entrypoint nice jointbuildgs:dev -n 19 python "$@" \
  > "$PAY/logs/$stamp-$tag.log" 2>&1
rc=$?
printf '%s %s rc=%s\n' "$stamp" "$tag" "$rc" >> "$PAY/logs/runs.log"
cat "$PAY/logs/$stamp-$tag.log"
exit "$rc"
