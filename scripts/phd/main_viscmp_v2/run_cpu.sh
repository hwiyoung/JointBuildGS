#!/usr/bin/env bash
# PHD-MAIN-VISCMP-v2 thin runner of one CPU step in jointbuildgs:dev (network off, no GPU, nice 19, memory cap 8 GB by default).
#   [CPUS=8] [MEM=8] bash run_cpu.sh <tag> <script.py> [args ...]
# Mounts: /art = JointBuildGS-artifacts (ro), /vc = this payload (rw), /repo (ro), /docs = docs/experiments/phd/main_viscmp_v2 (rw), fonts.
# Log /vc/logs/<tag>.log and a line in /vc/logs/queue.log. scientific_verdict: null.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
VC="$ART/phase-payloads/phd/main_viscmp_v2/PHD-MAIN-VISCMP-v2"; DOCS="$REPO/docs/experiments/phd/main_viscmp_v2"
tag=$1; shift; script=$1; shift
mkdir -p "$VC/logs"; [ -f "$VC/logs/$tag.log" ] && mv "$VC/logs/$tag.log" "$VC/logs/$tag.$(date +%H%M%S).log"
t0=$SECONDS
docker run --rm --name "jbgs-vc-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus "${CPUS:-8}" --memory "${MEM:-8}g" --shm-size 2g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS="${CPUS:-8}" -e CUDA_VISIBLE_DEVICES="" \
  -v "$ART:/art:ro" -v "$VC:/vc" -v "$REPO:/repo:ro" -v "$DOCS:/docs" -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/main_viscmp_v2 --entrypoint nice jointbuildgs:dev -n 19 python "$script" "$@" > "$VC/logs/$tag.log" 2>&1
rc=$?; echo "$(date '+%m-%d %H:%M:%S') $tag rc=$rc $((SECONDS-t0))s" | tee -a "$VC/logs/queue.log"
exit $rc
