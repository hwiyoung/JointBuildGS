#!/usr/bin/env bash
# Read-only inherited inputs; task-local outputs. No GPU access or training.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_candpick_v1/PHD-MAIN-CANDPICK-v1"
DOC="$REPO/docs/experiments/phd/main_candpick_v1"
CFG="$REPO/configs/phd/main_candpick_v1"
mkdir -p "$OUT/logs" "$DOC" "$CFG"
tag=$1; shift
nice -n 19 docker run --rm --network none --read-only \
  --user "$(id -u):$(id -g)" --cpus 4 --memory "${CANDPICK_MEMORY:-8g}" --memory-swap "${CANDPICK_MEMORY:-8g}" \
  --tmpfs /tmp:rw,size=512m,mode=1777 \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=1 -e TZ=Asia/Seoul \
  -e CANDPICK_COMMIT="$(git -C "$REPO" rev-parse HEAD)" \
  -e CANDPICK_IMAGE="$(docker image inspect -f '{{.Id}}' jointbuildgs:dev)" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" \
  -v "$DOC:/docs:rw" -v "$CFG:/config:rw" \
  -w /repo --entrypoint python jointbuildgs:dev -B -u "$@" \
  2>&1 | tee "$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
