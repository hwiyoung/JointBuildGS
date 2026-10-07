#!/usr/bin/env bash
# PHD-MAIN-STAGE1-v1: GeoGS inputs of one site with the official preprocessing (geogs_prep.py) in jointbuildgs:geogs-official-db40c95-v1
# (CPU, network off). Mounts: /source the untouched official checkout (ro), /s0 stage-0 payload (ro), /dr discard payload (ro),
# /out this payload, /repo (ro). SLOT=1: under the slot lock (at most two trainings + one other Docker job).
#   SLOT=1 bash run_geogs_prep.sh <site>
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
OUT="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"; DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"
SRC="$PH/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/sources/GeoGS"
site=$1; tag="geogs_prep_$site"
mkdir -p "$OUT/logs"; [ -f "$OUT/logs/$tag.log" ] && mv "$OUT/logs/$tag.log" "$OUT/logs/$tag.$(date +%H%M%S).log"
[ "${SLOT:-0}" = "1" ] && { exec 9>>"$OUT/logs/slot0.lock"; flock 9; }
t0=$SECONDS
docker run --rm --name "jbgs-s1-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus 16 --memory 46g --shm-size 4g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS=16 \
  -v "$SRC:/source:ro" -v "$S0:/s0:ro" -v "$DR:/dr:ro" -v "$OUT:/out" -v "$REPO:/repo:ro" \
  -w /repo/scripts/phd/main_stage1_v1 --entrypoint python jointbuildgs:geogs-official-db40c95-v1 geogs_prep.py "$site" > "$OUT/logs/$tag.log" 2>&1
rc=$?; echo "$(date +%H:%M:%S) $tag rc=$rc $((SECONDS-t0))s" | tee -a "$OUT/logs/queue.log"
exit $rc
