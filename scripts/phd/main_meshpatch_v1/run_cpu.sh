#!/usr/bin/env bash
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PH="$ART/phase-payloads/phd"
OUT="$PH/main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1"
mkdir -p "$OUT/logs" "$OUT/cache" "$REPO/docs/experiments/phd/main_meshpatch_v1" "$REPO/configs/phd/main_meshpatch_v1"
tag=$1; shift
memory_limit=4g
cpu_limit=2
if [[ ${1:-} == --large ]]; then
  shift
  memory_limit=40g
  cpu_limit=8
  exec 9<"$PH/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock"
  flock -x 9
  stable=0
  while (( stable < 60 )); do
    available=$(awk '/MemAvailable/{printf "%d", $2/1024/1024}' /proc/meminfo)
    if (( available >= 56 )); then stable=$((stable+5)); else stable=0; fi
    printf 'admission available=%s GiB stable=%ss/60s\n' "$available" "$stable"
    sleep 5
  done
fi
log="$OUT/logs/${tag}_$(date +%Y%m%dT%H%M%S).log"
tar -czf "${log%.log}.source_snapshot.tar.gz" -C "$REPO" scripts/phd/main_meshpatch_v1 configs/phd/main_meshpatch_v1
git -C "$REPO" rev-parse HEAD > "${log%.log}.commit.txt"
set +e
docker run --rm --name "jbgs-meshpatch-$tag" --network none --user "$(id -u):$(id -g)" \
  --cpus "$cpu_limit" --memory "$memory_limit" --memory-swap "$memory_limit" --shm-size 1g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e NUMBA_CACHE_DIR=/out/cache/numba -e PYTHONPATH=/out/cache/python \
  -e MPLCONFIGDIR=/out/cache/mpl -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e TZ=Asia/Seoul \
  -v "$ART:/art:ro" -v "$PH:/ph:ro" -v "$OUT:/out" -v "$REPO:/repo:ro" \
  -v "$REPO/configs/phd/main_meshpatch_v1:/config" \
  -v "$REPO/docs/experiments/phd/main_meshpatch_v1:/docs" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/main_meshpatch_v1 --entrypoint python jointbuildgs:dev "$@" 2>&1 | tee "$log"
exit "${PIPESTATUS[0]}"
