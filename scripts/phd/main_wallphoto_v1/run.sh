#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
OUT="$ART/phase-payloads/phd/main_wallphoto_v1/PHD-MAIN-WALLPHOTO-v1"
DOCS="$REPO/docs/experiments/phd/main_wallphoto_v1"
CFG="$REPO/configs/phd/main_wallphoto_v1"
mode=$1; tag=$2; shift 2
mkdir -p "$OUT/logs" "$OUT/tmp"
memory=4g; cpus=2; cache=0; minimum=60
if [[ "$mode" == large ]]; then memory=32g; cpus=8; cache=8589934592; minimum=88; fi
if [[ "$mode" == bounded ]]; then memory=12g; cpus=8; cache=2147483648; minimum=68; fi
if [[ "$mode" == audit ]]; then memory=2g; cpus=1; cache=0; minimum=18; fi
start=$(date +%s)
while true; do
  available=$(awk '/MemAvailable/{printf "%d", $2/1024/1024}' /proc/meminfo)
  if (( available >= minimum )); then break; fi
  printf '%s wait: MemAvailable=%s GiB required=%s GiB; MESHPATCH priority\n' "$(date -Iseconds)" "$available" "$minimum" | tee -a "$OUT/logs/resource_wait.log"
  sleep 15
done
printf '%s %s %s\n' "$(date -Iseconds)" "$tag" "$(($(date +%s)-start))" >> "$OUT/logs/admission_wait_seconds.txt"
exec 9>"$OUT/task.lock"
flock -x 9
nice -n 19 docker run --rm --read-only --network none --name "jbgs-wallphoto-$tag" \
  --user "$(id -u):$(id -g)" --cpus "$cpus" --memory "$memory" --memory-swap "$memory" \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 -e OMP_NUM_THREADS="$cpus" \
  -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e TZ=Asia/Seoul \
  -e TMPDIR=/out/tmp -e MPLCONFIGDIR=/out/tmp/mpl -e XDG_CACHE_HOME=/out/tmp/cache \
  -e PHOTOCHECK_RAM_CACHE_BYTES="$cache" \
  --tmpfs /out/tmp/image_cache_ram:rw,size=9g,mode=1777 \
  -e PHOTOCHECK_COMMIT="$(git -C "$REPO" rev-parse HEAD)" \
  -e PHOTOCHECK_IMAGE="$(docker image inspect -f '{{.Id}}' jointbuildgs:dev)" \
  -v "$REPO:/repo:ro" -v "$ART:/art:ro" -v "$OUT:/out:rw" \
  -v "$DOCS:/docs:rw" -v "$CFG:/cfg:rw" -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /out --entrypoint nice jointbuildgs:dev -n 19 python -B -u \
  "/repo/scripts/phd/main_wallphoto_v1/$@" \
  2>&1 | tee "$OUT/logs/${tag}_$(date +%Y%m%dT%H%M%S).log"
