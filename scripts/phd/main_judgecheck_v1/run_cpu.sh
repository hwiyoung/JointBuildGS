#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1"
CFG="$REPO/configs/phd/main_judgecheck_v1"
DOCS="$REPO/docs/experiments/phd/main_judgecheck_v1"
mkdir -p "$OUT/logs" "$OUT/tmp" "$CFG" "$DOCS"
tag=$1; shift
exec 9>"$OUT/task.lock"
flock -x 9
if [[ "$1" == photo_prepare_reply2.py ]]; then
  mkdir -p "$OUT/r2/photo_prepared"
  exec 8>"$OUT/r2/photo_prepared/$2.lock"
  flock -x 8
fi
nice -n 19 docker run --rm --read-only --network none --runtime runc \
  --name "jbgs-judgecheck-$tag" --user "$(id -u):$(id -g)" \
  --cpus 4 --memory 32g --memory-swap 32g \
  -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache \
  -e TZ=Asia/Seoul \
  -e JUDGECHECK_COMMIT="$(GIT_OPTIONAL_LOCKS=0 git -C "$REPO" rev-parse HEAD)" \
  -e JUDGECHECK_IMAGE="$(docker image inspect -f '{{.Id}}' jointbuildgs:dev)" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" \
  -v "$DOCS:/docs:rw" -v "$CFG:/cfg:rw" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro -w /out \
  --entrypoint nice jointbuildgs:dev -n 19 python -B -u \
  "/repo/scripts/phd/main_judgecheck_v1/$@" \
  2>&1 | tee "$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
