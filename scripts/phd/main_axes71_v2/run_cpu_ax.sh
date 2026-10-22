#!/usr/bin/env bash
# PHD-MAIN-AXES71-v2 thin runner of one CPU step in jointbuildgs:dev (network off, no GPU; every input read-only except this payload and,
# for the steps that write the repository's docs, /docs = docs/experiments/phd/main_axes71_v2).
#   [CPUS=8] [MEM=24] bash run_cpu_ax.sh <tag> <script.py> [args ...]
# Mounts: /ph = phase-payloads/phd (ro) with THIS payload read-write at /ph/main_axes71_v2/PHD-MAIN-AXES71-v2, /out = the stage-1
# payload (ro), /s0 /mt /mf /dr /prep /diag /art (ro) as the distance task (scripts/phd/main_dist71_v1/run_cpu_dm.sh), /repo (ro), fonts.
# Log: logs/<tag>.log (an existing log is renamed first) and a line in logs/queue.log. scientific_verdict: null.
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
AX="$PH/main_axes71_v2/PHD-MAIN-AXES71-v2"; S1="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"
MT="$PH/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1"; MF="$PH/metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1"; DIAG="$PH/main_stage1_diag_v1/PHD-MAIN-STAGE1-DIAG-v1"
DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; PREP="$PH/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
DOCS="$REPO/docs/experiments/phd/main_axes71_v2"
tag=$1; shift; script=$1; shift
mkdir -p "$AX/logs" "$DOCS"; [ -f "$AX/logs/$tag.log" ] && mv "$AX/logs/$tag.log" "$AX/logs/$tag.$(date +%H%M%S).log"
t0=$SECONDS
docker run --rm --name "jbgs-ax-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus "${CPUS:-8}" --memory "${MEM:-24}g" --shm-size 4g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS="${CPUS:-8}" -e TZ=Asia/Seoul \
  -e CUDA_VISIBLE_DEVICES="" -e SHARD="${SHARD:-0}" -e SHARDS="${SHARDS:-1}" \
  -v "$PH:/ph:ro" -v "$AX:/ph/main_axes71_v2/PHD-MAIN-AXES71-v2" -v "$S1:/out:ro" -v "$S0:/s0:ro" -v "$MT:/mt:ro" -v "$MF:/mf:ro" \
  -v "$DR:/dr:ro" -v "$PREP:/prep:ro" -v "$DIAG:/diag:ro" -v "$ART:/art:ro" -v "$REPO:/repo:ro" -v "$DOCS:/docs" \
  -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/main_axes71_v2 --entrypoint python jointbuildgs:dev "$script" "$@" > "$AX/logs/$tag.log" 2>&1
rc=$?; echo "$(date '+%m-%d %H:%M:%S') $tag rc=$rc $((SECONDS-t0))s" | tee -a "$AX/logs/queue.log"
exit $rc
