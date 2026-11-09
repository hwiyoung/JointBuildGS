#!/usr/bin/env bash
set -euo pipefail
R=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$R/../JointBuildGS-artifacts")
O="$ART/phase-payloads/phd/main_procfig_v1/PHD-MAIN-PROCFIG-v1"
mode=$1; shift
image=jointbuildgs:dev
device=(--runtime runc -e NVIDIA_VISIBLE_DEVICES=void -e CUDA_VISIBLE_DEVICES=)
if [[ "$mode" == torch ]]; then image=sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be; fi
if [[ "$mode" == gpu ]]; then image=sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be; device=(--gpus device=0); fi
nice -n 19 docker run --rm --read-only --network none --name "jbgs-procfig-$mode" \
 --user "$(id -u):$(id -g)" --cpus 6 --memory 32g --memory-swap 32g "${device[@]}" \
 -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
 -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache -e TZ=Asia/Seoul \
 -e PROCFIG_COMMIT="$(git -C "$R" rev-parse HEAD)" -e PROCFIG_IMAGE="$(docker image inspect -f '{{.Id}}' "$image")" \
 -v "$R:/repo:ro" -v "$ART:/art:ro" -v "$ART:/artifacts/JointBuildGS:ro" \
 -v "$O:/out:rw" -v "$R/configs/phd/main_procfig_v1:/cfg:rw" -v "$R/docs/experiments/phd/main_procfig_v1:/docs:rw" \
 -v "$R/src/phd/forks/GeoGS-conf-guided-v1-r23:/source:ro" \
 -w /out --entrypoint /bin/bash "$image" -c 'if [ -f /opt/geogs/lib/libstdc++.so.6 ]; then export LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6; fi; exec python -B -u "/repo/scripts/phd/main_procfig_v1/$@"' bash "$@" \
 > "$O/logs/$(date -u +%Y%m%dT%H%M%SZ)_${mode}_$(basename "$1").log" 2>&1
