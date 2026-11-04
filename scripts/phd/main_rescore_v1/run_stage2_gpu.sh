#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1"
job=$1;program=${2:-render_model.py}
mapfile -t fields < <(python3 - "$OUT/$job" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));print(x['image']);print(x['renderer']);print(x['key'])
PY
)
image=${fields[0]};source=${fields[1]};key=${fields[2]}
min_free=8192;fraction=.25
if [[ "$key" == B173_b0__* ]]; then min_free=16384;fraction=.60;fi
source=${source/#\/repo/$REPO};source=${source/#\/art/$ART}
wait_start=$(date +%s)
while true; do
 gpu=$(nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits | awk -F, -v required="$min_free" '$2>=required {if ($2>best) {best=$2; id=$1; ok=1}} END {if(ok)print id}')
 if [[ -n "$gpu" ]]; then break; fi
 sleep 30
done
wait_seconds=$(( $(date +%s) - wait_start ))
nice -n 19 docker run --rm --read-only --network none --gpus "device=$gpu" \
 --name "jbgs-rescore-s2-render-${key//_/-}" --user "$(id -u):$(id -g)" --cpus 4 --memory 32g --memory-swap 32g \
 -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
 -e TMPDIR=/out/addendum3_stage2/tmp -e MPLCONFIGDIR=/out/addendum3_stage2/tmp/mpl -e XDG_CACHE_HOME=/out/addendum3_stage2/tmp/cache -e TZ=Asia/Seoul -e RESCORE_GPU_WAIT_SECONDS="$wait_seconds" -e RESCORE_RENDER_GPU_FRACTION="$fraction" \
 -e RESCORE_IMAGE="$(docker image inspect -f '{{.Id}}' "$image")" -e RESCORE_COMMIT="$(git -C "$REPO" rev-parse HEAD)" \
 -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$source:/source:ro" -v "$OUT:/out:rw" \
 -v "$REPO/configs/phd/main_rescore_v1:/cfg:ro" -v "$REPO/docs/experiments/phd/main_rescore_v1:/docs:rw" \
 -e RESCORE_OUTPUT_ROOT=/out/addendum3_stage2 -e RESCORE_DOC_ROOT=/docs/addendum3_stage2 -e RESCORE_CELLS_ROOT=/out/cells_v2 -w /out/addendum3_stage2 --entrypoint /bin/bash "$image" -c 'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; exec nice -n 19 python -B -u "/repo/scripts/phd/main_rescore_v1/$2" "$1"' bash "/out/$job" "$program" \
 2>&1 | tee "$OUT/addendum3_stage2/logs/render_${key}_$(date -u +%Y%m%dT%H%M%SZ).log"
