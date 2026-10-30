#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_candpick_v1/PHD-MAIN-CANDPICK-v1"
gpu=$1; tag=$2; shift 2
mkdir -p "$OUT/logs" "$OUT/cache"
exec 9>"$OUT/gpu${gpu}.lock"
flock -x 9
gpu_uuid=$(nvidia-smi --id="$gpu" --query-gpu=uuid --format=csv,noheader)
while nvidia-smi --query-compute-apps=gpu_uuid,process_name --format=csv,noheader \
    | rg --fixed-strings "$gpu_uuid" \
    | rg -v '/usr/libexec/gnome-remote-desktop-daemon$' >/dev/null; do
  sleep 15
done
docker run --rm --network none --read-only --gpus "device=$gpu" \
  --name "jbgs-candpick-${tag}" --user "$(id -u):$(id -g)" \
  --cpus 8 --memory 24g --memory-swap 24g --shm-size 2g \
  --tmpfs /tmp:rw,size=2g,mode=1777 \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e TZ=Asia/Seoul \
  -e OMP_NUM_THREADS=8 -e OPENBLAS_NUM_THREADS=1 -e MAX_JOBS=4 \
  -e TORCH_EXTENSIONS_DIR=/out/cache/torch_extensions -e NUMBA_CACHE_DIR=/out/cache/numba \
  -e XDG_CACHE_HOME=/out/cache -e MPLCONFIGDIR=/tmp/mpl \
  -e PYTHONPATH=/repo -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e CANDPICK_COMMIT="$(git -C "$REPO" rev-parse HEAD)" \
  -e CANDPICK_IMAGE="$(docker image inspect -f '{{.Id}}' jointbuildgs:dev)" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" \
  -v "$REPO/configs/phd/main_candpick_v1:/config:rw" \
  -v "$REPO/docs/experiments/phd/main_candpick_v1:/docs:rw" \
  -w /repo --entrypoint python jointbuildgs:dev -B -u "$@" \
  2>&1 | tee "$OUT/logs/${tag}_$(date -u +%Y%m%dT%H%M%SZ).log"
