#!/usr/bin/env bash
# PHD-MAIN-JUDGENUM-v1: only this task's four paths are writable.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_judgenum_v1/PHD-MAIN-JUDGENUM-v1"
DOCS="$REPO/docs/experiments/phd/main_judgenum_v1"
CFG="$REPO/configs/phd/main_judgenum_v1"
tag=$1; shift
mkdir -p "$OUT/logs" "$OUT/tmp" "$DOCS" "$CFG"
exec 9>"$OUT/task.lock"
flock -x 9
nice -n 19 docker run --rm --read-only --network none --runtime runc \
  --name "jbgs-judgenum-$tag" --user "$(id -u):$(id -g)" \
  --cpus 8 --memory 32g --memory-swap 32g \
  -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache \
  -e TZ=Asia/Seoul -e JUDGENUM_COMMIT="$(GIT_OPTIONAL_LOCKS=0 git -C "$REPO" rev-parse HEAD)" \
  -e JUDGENUM_IMAGE="$(docker image inspect -f '{{.Id}}' jointbuildgs:dev)" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" \
  -v "$DOCS:/docs:rw" -v "$CFG:/cfg:rw" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro -w /out \
  --entrypoint nice jointbuildgs:dev -n 19 python -B -u \
  "/repo/scripts/phd/main_judgenum_v1/$@" \
  2>&1 | tee "$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
