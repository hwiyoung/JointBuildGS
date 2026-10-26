#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1"
DOCS="$REPO/docs/experiments/phd/main_photocheck_v1"
CFG="$REPO/configs/phd/main_photocheck_v1"
mkdir -p "$OUT/logs" "$OUT/tmp" "$DOCS" "$CFG"
mode=$1; tag=$2; shift 2
gpu=()
if [[ "$mode" == gpu ]]; then
  gpu=(--gpus device=1)
  wait_start=$(date +%s)
  gpu_uuid=$(nvidia-smi --id=1 --query-gpu=uuid --format=csv,noheader)
  while nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | rg -q --fixed-strings "$gpu_uuid"; do
    printf 'GPU 1 in use; waiting %s seconds\n' "$(($(date +%s)-wait_start))"
    sleep 15
  done
  printf '%s\n' "$(($(date +%s)-wait_start))" > "$OUT/logs/${tag}_gpu_wait_seconds.txt"
fi
nice -n 19 docker run --rm --read-only --network none "${gpu[@]}" \
  --user "$(id -u):$(id -g)" --cpus 32 --memory 32g --memory-swap 32g \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e OMP_NUM_THREADS=8 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache \
  -e NUMBA_CACHE_DIR=/out/tmp/numba -e TZ=Asia/Seoul \
  -e PHOTOCHECK_COMMIT="$(git -C "$REPO" rev-parse HEAD)" \
  -e PHOTOCHECK_IMAGE="$(docker image inspect -f '{{.Id}}' jointbuildgs:dev)" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" \
  -v "$DOCS:/docs:rw" -v "$CFG:/cfg:rw" -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /out --entrypoint nice jointbuildgs:dev -n 19 python -B -u \
  "/repo/scripts/phd/main_photocheck_v1/$@" \
  2>&1 | tee "$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
