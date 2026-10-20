#!/usr/bin/env bash
# PHD-MAIN-PHOTOFIG-v1 thin runner of one CPU step in jointbuildgs:dev (network off, no GPU, nice 19, memory cap 8 GB by default).
#   [CPUS=8] [MEM=8] bash run_cpu.sh <tag> <script.py> [args ...]
# Mounts: /art = JointBuildGS-artifacts (ro) with THIS payload read-write at /pf, /repo (ro), /docs = docs/experiments/phd/main_photofig_v1
# (rw), fonts. Writes only /pf and /docs. Log /pf/logs/<tag>.log and a line in /pf/logs/queue.log. scientific_verdict: null.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
PF="$PH/main_photofig_v1/PHD-MAIN-PHOTOFIG-v1"; DOCS="$REPO/docs/experiments/phd/main_photofig_v1"
tag=$1; shift; script=$1; shift
mkdir -p "$PF/logs"; [ -f "$PF/logs/$tag.log" ] && mv "$PF/logs/$tag.log" "$PF/logs/$tag.$(date +%H%M%S).log"
t0=$SECONDS
docker run --rm --name "jbgs-pf-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus "${CPUS:-8}" --memory "${MEM:-8}g" --shm-size 2g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS="${CPUS:-8}" \
  -e CUDA_VISIBLE_DEVICES="" \
  -v "$ART:/art:ro" -v "$PF:/pf" -v "$REPO:/repo:ro" -v "$DOCS:/docs" -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/main_photofig_v1 --entrypoint nice jointbuildgs:dev -n 19 python "$script" "$@" > "$PF/logs/$tag.log" 2>&1
rc=$?; echo "$(date '+%m-%d %H:%M:%S') $tag rc=$rc $((SECONDS-t0))s" | tee -a "$PF/logs/queue.log"
exit $rc
