#!/usr/bin/env bash
# PHD-MAIN-METRICS-TRIAL-v1 thin runner of one CPU step in jointbuildgs:dev (network off, inputs read-only).
#   bash run_cpu.sh <tag> <script.py> [args ...]
# Mounts: /art artifacts (ro), /s0 stage-0 payload (ro), /dr discard payload (ro), /prep prep payload (ro), /out this payload,
# /repo repository (ro). Log: logs/<tag>.log (an existing log is renamed first); queue.log line "<time> <tag> rc=<rc> <s>s".
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PH="$ART/phase-payloads/phd"
OUT="$PH/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"
DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; PREP="$PH/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
tag=$1; shift; script=$1; shift
mkdir -p "$OUT/logs"; [ -f "$OUT/logs/$tag.log" ] && mv "$OUT/logs/$tag.log" "$OUT/logs/$tag.$(date +%H%M%S).log"
t0=$SECONDS
docker run --rm --name "jbgs-mt-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus 16 --shm-size 8g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS=16 -e TZ=Asia/Seoul \
  -v "$ART:/art:ro" -v "$S0:/s0:ro" -v "$DR:/dr:ro" -v "$PREP:/prep:ro" -v "$OUT:/out" -v "$REPO:/repo:ro" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro -w /repo/scripts/phd/metrics_trial_v1 --entrypoint python jointbuildgs:dev "$script" "$@" > "$OUT/logs/$tag.log" 2>&1
rc=$?; echo "$(date +%H:%M:%S) $tag rc=$rc $((SECONDS-t0))s" | tee -a "$OUT/logs/queue.log"
exit $rc
