#!/usr/bin/env bash
# PHD-MAIN-FIXTEST-v1 thin runner of one post step in jointbuildgs:dev = stage 3's run_cpu3.sh with THIS payload read-write at
# /ph/main_fixtest_v1/PHD-MAIN-FIXTEST-v1 and the working directory scripts/phd/main_fixtest_v1 (ft_step.py).
#   [CPUS=12] [MEM=40] bash run_step_ft.sh <tag> ft_step.py <script.py> [args ...]
# Mounts: /ph = phase-payloads/phd (ro) with this payload rw, /out = the stage-1 payload (ro; the stage-1 helpers read it as /out),
# /s0 /mt /mf /dr /prep /diag /art (ro), /repo (ro), fonts. Log logs/<tag>.log; logs/queue.log line. scientific_verdict: null.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
FT="$PH/main_fixtest_v1/PHD-MAIN-FIXTEST-v1"; S1="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"
MT="$PH/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1"; MF="$PH/metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1"; DIAG="$PH/main_stage1_diag_v1/PHD-MAIN-STAGE1-DIAG-v1"
DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; PREP="$PH/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
tag=$1; shift; script=$1; shift
mkdir -p "$FT/logs"; [ -f "$FT/logs/$tag.log" ] && mv "$FT/logs/$tag.log" "$FT/logs/$tag.$(date +%H%M%S).log"
t0=$SECONDS
docker run --rm --name "jbgs-fts-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus "${CPUS:-12}" --memory "${MEM:-40}g" --shm-size 8g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS="${CPUS:-12}" -e TZ=Asia/Seoul \
  -v "$PH:/ph:ro" -v "$FT:/ph/main_fixtest_v1/PHD-MAIN-FIXTEST-v1" -v "$S1:/out:ro" -v "$S0:/s0:ro" -v "$MT:/mt:ro" -v "$MF:/mf:ro" \
  -v "$DR:/dr:ro" -v "$PREP:/prep:ro" -v "$DIAG:/diag:ro" -v "$ART:/art:ro" -v "$REPO:/repo:ro" -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/main_fixtest_v1 --entrypoint python jointbuildgs:dev "$script" "$@" > "$FT/logs/$tag.log" 2>&1
rc=$?; echo "$(date '+%m-%d %H:%M:%S') $tag rc=$rc $((SECONDS-t0))s" | tee -a "$FT/logs/queue.log"
exit $rc
