#!/usr/bin/env bash
# PHD-MAIN-TRAINUNIT-v2 CPU container: as run_cpu.sh, but /tu = the v2 payload (rw), /tu1 = the v1 payload (ro), and the
# container's docs folder of this task = docs/experiments/phd/main_trainunit_v1/v2 (so v1 tables are never overwritten).
# A host-memory guard kills only this container if host MemAvailable falls below 20 GB.
#   bash run2_cpu.sh <tag> <cpus> <memory> <script.py> [args...]
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts
TU1="$ART/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1"
TU="$ART/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v2"
DOCS="$REPO/docs/experiments/phd/main_trainunit_v1/v2"
tag=$1; cpus=$2; mem=$3; shift 3
mkdir -p "$TU/tmp" "$TU/logs" "$DOCS/tables" "$DOCS/figures"
name="jbgs-trainunit2-$tag"
nice -n 10 docker run --rm --read-only --network none --runtime runc \
  --name "$name" --user "$(id -u):$(id -g)" --cpus "$cpus" --memory "$mem" --memory-swap "$mem" \
  -e CUDA_VISIBLE_DEVICES= -e NVIDIA_VISIBLE_DEVICES=void -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 -e NUMPY_MADVISE_HUGEPAGE=0 \
  -e TMPDIR=/tu/tmp -e MPLCONFIGDIR=/tu/tmp/mpl -e XDG_CACHE_HOME=/tu/tmp/cache -e TZ=Asia/Seoul \
  -v "$REPO:/repo:ro" -v "$DOCS:/repo/docs/experiments/phd/main_trainunit_v1:rw" -v "$REPO/docs/experiments/phd/main_trainunit_v1:/docs1:ro" \
  -v "$ART:/art:ro" -v "$ART:/artifacts/JointBuildGS:ro" -v "$TU:/tu:rw" -v "$TU1:/tu1:ro" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro -w /tu --entrypoint python jointbuildgs:dev -B -u \
  "/repo/scripts/phd/main_trainunit_v1/$@" > "$TU/logs/$tag.log" 2>&1 &
pid=$!
while kill -0 $pid 2>/dev/null; do
  avail=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)
  if [ "$avail" -lt 20 ]; then
    docker kill "$name" >/dev/null 2>&1
    echo "- $(date -Iseconds): 호스트 보호: 가용 ${avail} GB < 20 GB → 이 작업 컨테이너 $name 멈춤." >> "$DOCS/issues.md"
    break
  fi
  sleep 5
done
wait $pid; rc=$?
tail -5 "$TU/logs/$tag.log"
exit $rc
