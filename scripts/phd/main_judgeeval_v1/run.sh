#!/bin/bash
# PHD-MAIN-JUDGEEVAL-v1 container launcher (CPU only, no training). Reads artifacts read-only; writes only /out (PH/main_judgeeval_v1/PHD-MAIN-JUDGEEVAL-v1), /docs, /cfg.
# usage: run.sh <script.py> [args...]
R=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(cd "$R/../JointBuildGS-artifacts" && pwd); PH=$ART/phase-payloads/phd
O=$PH/main_judgeeval_v1/PHD-MAIN-JUDGEEVAL-v1; D=$R/docs/experiments/phd/main_judgeeval_v1; C=$R/configs/phd/main_judgeeval_v1; mkdir -p "$O/tmp/mpl" "$D"
exec docker run --rm --network none --user "$(id -u):$(id -g)" --cpus ${GT_CPUS:-32} --memory ${GT_MEM:-32g} --shm-size 2g \
  --runtime runc -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS=4 -e TZ=Asia/Seoul -e GT_STAGE=${GT_STAGE:-ga} -e GT_WORKERS=${GT_WORKERS:-12} \
  -e MPLCONFIGDIR=/out/tmp/mpl -e TMPDIR=/out/tmp \
  -v "$R:/repo:ro" -v "$ART:/art:ro" -v "$PH/main_judgegt_v1/PHD-MAIN-JUDGEGT-v1:/gt:ro" -v "$O:/out:rw" -v "$D:/docs:rw" -v "$C:/cfg:rw" -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/main_judgeeval_v1 --entrypoint nice sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 -n 19 python -B "$@"
