#!/bin/bash
# PHD-MAIN-JUDGEVIDEO-v1 container launcher (CPU). Reads the TRAINLOG payload/docs/config read-only; writes only /out (PH/main_judgevideo_v1) and /jdocs.
# usage: jv_run.sh <script.py> [args...]   env CV2_VARIANT=r6 is set (the r6 static layers of the existing video)
# jv_video.py: ffmpeg = imageio-ffmpeg 0.5.1 wheel (static ffmpeg 4.2.2, libx264) installed once with pip --target into /out/tmp/pylib (the earlier video image
# jointbuildgs:geogs-da3-3d835ec-v1 is no longer on this host); PYTHONPATH points there.
R=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(cd "$R/../JointBuildGS-artifacts" && pwd); PH=$ART/phase-payloads/phd
O=$PH/main_judgevideo_v1/PHD-MAIN-JUDGEVIDEO-v1; D=$R/docs/experiments/phd/main_judgevideo_v1; mkdir -p "$O/tmp/mpl" "$D"
exec docker run --rm --network none --user "$(id -u):$(id -g)" --cpus 8 --memory 24g --shm-size 2g \
  --runtime runc -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES= \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS=4 -e CV2_VARIANT=r6 -e TZ=Asia/Seoul \
  -e MPLCONFIGDIR=/out/tmp/mpl -e TMPDIR=/out/tmp -e PYTHONPATH=/out/tmp/pylib \
  -v "$R:/repo:ro" -v "$ART:/art:ro" -v "$PH:/ph:ro" \
  -v "$PH/main_trainlog_v1/PHD-MAIN-TRAINLOG-v1:/tl:ro" -v "$R/docs/experiments/phd/main_trainlog_v1:/docs:ro" -v "$R/configs/phd/main_trainlog_v1:/cfg:ro" \
  -v "$O:/out:rw" -v "$D:/jdocs:rw" -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/main_judgevideo_v1 --entrypoint python ${JV_IMAGE:-sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774} -B "$@"
