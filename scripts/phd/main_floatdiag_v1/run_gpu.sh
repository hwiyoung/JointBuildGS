#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PH="$ART/phase-payloads/phd"
OUT="$PH/main_floatdiag_v1/PHD-MAIN-FLOATDIAG-v1"
gpu=$1
site=$2
tag=$3
shift 3
exec 8<"$PH/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/photo_gpu_${gpu}.lock"
flock -x 8
busy=$(nvidia-smi -i "$gpu" --query-compute-apps=pid --format=csv,noheader)
if [[ -n "$busy" ]]; then
  printf 'GPU %s has an active compute process; no launch.\n' "$gpu"
  exit 75
fi
mkdir -p "$OUT/logs"
log="$OUT/logs/${tag}_$(date +%Y%m%dT%H%M%S).log"
tar -czf "${log%.log}.source_snapshot.tar.gz" -C "$REPO" scripts/phd/main_floatdiag_v1 configs/phd/main_floatdiag_v1
git -C "$REPO" rev-parse HEAD > "${log%.log}.commit.txt"
set +e
docker run --rm --name "jbgs-floatdiag-$tag" --gpus "device=$gpu" --network none \
  --user "$(id -u):$(id -g)" --cpus 4 --memory 24g --shm-size 2g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=4 -e OPENBLAS_NUM_THREADS=4 \
  -e MPLCONFIGDIR=/out/cache/mpl -e TORCH_HOME=/weights/torch -e TZ=Asia/Seoul \
  -e "JBGS_SPLIT_JSON=/p/fork_inputs/s61/$site/split.json" -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -v "$ART:/artifacts/JointBuildGS:ro" -v "$PH:/ph:ro" \
  -v "$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1:/p:ro" \
  -v "$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1:/s0:ro" \
  -v "$PH/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights:/weights:ro" \
  -v "$OUT:/out" -v "$OUT:/o" -v "$REPO:/repo:ro" \
  -v "$REPO/src/phd/forks/GeoGS-conf-guided-v1-r17:/source:ro" \
  -v "$REPO/configs/phd/main_floatdiag_v1:/config" -v "$REPO/docs/experiments/phd/main_floatdiag_v1:/docs" \
  -w /source --entrypoint python jointbuildgs:geogs-conf-guided-v1 "$@" 2>&1 | tee "$log"
exit "${PIPESTATUS[0]}"
