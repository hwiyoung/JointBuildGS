#!/usr/bin/env bash
# PHD-MAIN-FIXTEST-v1 thin runner of one CPU step in jointbuildgs:dev (network off; every input read-only except this payload).
#   [CPUS=8] [MEM=24] bash run_cpu_ft.sh <tag> <script.py> [args ...]
# Mounts: /out = this payload (rw); /ph = phase-payloads/phd (ro, this payload also reachable there read-only); /s0 /s1 /dr /prep /art
# (ro); /repo (ro); fonts. Working directory /repo/scripts/phd/main_fixtest_v1. Log logs/<tag>.log (an existing log is renamed);
# logs/queue.log line. scientific_verdict: null.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
FT="$PH/main_fixtest_v1/PHD-MAIN-FIXTEST-v1"; S1="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"
DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; PREP="$PH/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
tag=$1; shift; script=$1; shift
mkdir -p "$FT/logs"; [ -f "$FT/logs/$tag.log" ] && mv "$FT/logs/$tag.log" "$FT/logs/$tag.$(date +%H%M%S).log"
t0=$SECONDS
docker run --rm --name "jbgs-ft-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus "${CPUS:-8}" --memory "${MEM:-24}g" --shm-size 8g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS="${CPUS:-8}" -e TZ=Asia/Seoul \
  -v "$FT:/out" -v "$PH:/ph:ro" -v "$S1:/s1:ro" -v "$S0:/s0:ro" -v "$DR:/dr:ro" -v "$PREP:/prep:ro" -v "$ART:/art:ro" -v "$REPO:/repo:ro" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/main_fixtest_v1 --entrypoint python jointbuildgs:dev "$script" "$@" > "$FT/logs/$tag.log" 2>&1
rc=$?; echo "$(date '+%m-%d %H:%M:%S') $tag rc=$rc $((SECONDS-t0))s" | tee -a "$FT/logs/queue.log"
exit $rc
