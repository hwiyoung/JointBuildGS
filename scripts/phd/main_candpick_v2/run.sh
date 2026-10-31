#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_candpick_v2/PHD-MAIN-CANDPICK-v2"
CP1="$ART/phase-payloads/phd/main_candpick_v1/PHD-MAIN-CANDPICK-v1"
mode=$1; tag=$2; shift 2
mkdir -p "$OUT/logs" "$OUT/cache" "$OUT/tmp"
image=sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
opts=()
if [[ "$mode" != cpu ]]; then
  exec 9>"$OUT/gpu${mode}.lock"
  flock -x 9
  gpu_uuid=$(nvidia-smi --id="$mode" --query-gpu=uuid --format=csv,noheader)
  while nvidia-smi --query-compute-apps=gpu_uuid,process_name --format=csv,noheader | rg --fixed-strings "$gpu_uuid" | rg -v '/usr/libexec/gnome-remote-desktop-daemon$' >/dev/null; do
    sleep 15
  done
  opts+=(--gpus "device=$mode")
fi
nice -n 19 docker run --rm --network none --read-only "${opts[@]}" \
  --name "jbgs-candpick2-${tag}" --user "$(id -u):$(id -g)" \
  --cpus 6 --memory 24g --memory-swap 24g --shm-size 1g \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e TZ=Asia/Seoul \
  -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=1 -e MAX_JOBS=4 \
  -e TORCH_EXTENSIONS_DIR=/out/cache/torch_extensions -e NUMBA_CACHE_DIR=/out/cache/numba \
  -e XDG_CACHE_HOME=/out/cache -e MPLCONFIGDIR=/out/cache/mpl -e TMPDIR=/out/tmp \
  -e PYTHONPATH=/repo/scripts/phd/main_candpick_v2:/repo/scripts/phd/main_candpick_v1:/repo \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e CANDPICK_COMMIT="$(git -C "$REPO" rev-parse HEAD)" -e CANDPICK_IMAGE="$image" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$CP1:/cp1:ro" -v "$OUT:/out:rw" \
  -v "$REPO/configs/phd/main_candpick_v2:/config:rw" \
  -v "$REPO/docs/experiments/phd/main_candpick_v2:/docs:rw" \
  -w /repo --entrypoint python "$image" -B -u "$@" \
  2>&1 | tee "$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
