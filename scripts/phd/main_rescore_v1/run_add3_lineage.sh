#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1"
wait_start=$(date +%s)
while true; do
 gpu=$(nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits | awk -F, '$2>=8192 {if ($2>best) {best=$2; id=$1; ok=1}} END {if(ok)print id}')
 if [[ -n "$gpu" ]]; then break; fi
 sleep 30
done
nice -n 19 docker run --rm --read-only --network none --gpus "device=$gpu" --name jbgs-rescore-a3-lineage \
 --user "$(id -u):$(id -g)" --cpus 4 --memory 32g --memory-swap 32g \
 -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
 -e TMPDIR=/out/addendum3_stage1/tmp -e MPLCONFIGDIR=/out/addendum3_stage1/tmp/mpl -e TZ=Asia/Seoul \
 -e RESCORE_OUTPUT_ROOT=/out/addendum3_stage1 -e RESCORE_DOC_ROOT=/docs/addendum3_stage1 -e RESCORE_CELLS_ROOT=/out/cells_v2 \
 -e RESCORE_GPU_WAIT_SECONDS="$(( $(date +%s)-wait_start ))" \
 -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$REPO/src/phd/forks/GeoGS-conf-guided-v1-r23:/source:ro" \
 -v "$OUT:/out:rw" -v "$REPO/configs/phd/main_rescore_v1:/cfg:ro" -v "$REPO/docs/experiments/phd/main_rescore_v1:/docs:rw" \
 -w /out/addendum3_stage1 --entrypoint /bin/bash sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be -c 'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; exec nice -n 19 python -B -u /repo/scripts/phd/main_rescore_v1/add3_lineage_render.py' \
 2>&1 | tee "$OUT/addendum3_stage1/logs/lineage_$(date -u +%Y%m%dT%H%M%SZ).log"
