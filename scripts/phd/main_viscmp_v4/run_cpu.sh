#!/usr/bin/env bash
# PHD-MAIN-VISCMP-v4 thin runner of one CPU step in jointbuildgs:dev (network off, no GPU, nice 19, memory cap 24 GB by default: the
# distance task's GT and units are loaded). Mounts as the distance task's run_cpu_dm.sh (all read-only) + /vc = this payload (rw),
# /docs = docs/experiments/phd/main_viscmp_v4 (rw).   [CPUS=8] [MEM=24] bash run_cpu.sh <tag> <script.py> [args ...]
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
VC="$PH/main_viscmp_v4/PHD-MAIN-VISCMP-v4"; DOCS="$REPO/docs/experiments/phd/main_viscmp_v4"
S1="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"; MT="$PH/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1"
MF="$PH/metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1"; DIAG="$PH/main_stage1_diag_v1/PHD-MAIN-STAGE1-DIAG-v1"
DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; PREP="$PH/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
tag=$1; shift; script=$1; shift
mkdir -p "$VC/logs"; [ -f "$VC/logs/$tag.log" ] && mv "$VC/logs/$tag.log" "$VC/logs/$tag.$(date +%H%M%S).log"
t0=$SECONDS
docker run --rm --name "jbgs-vc4-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus "${CPUS:-8}" --memory "${MEM:-24}g" --shm-size 4g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS="${CPUS:-8}" -e TZ=Asia/Seoul -e CUDA_VISIBLE_DEVICES="" \
  -v "$PH:/ph:ro" -v "$S1:/out:ro" -v "$S0:/s0:ro" -v "$MT:/mt:ro" -v "$MF:/mf:ro" -v "$DR:/dr:ro" -v "$PREP:/prep:ro" -v "$DIAG:/diag:ro" \
  -v "$ART:/art:ro" -v "$VC:/vc" -v "$REPO:/repo:ro" -v "$DOCS:/docs" -v /usr/share/fonts/opentype/noto:/fonts:ro \
  -w /repo/scripts/phd/main_viscmp_v4 --entrypoint nice jointbuildgs:dev -n 19 python "$script" "$@" > "$VC/logs/$tag.log" 2>&1
rc=$?; echo "$(date '+%m-%d %H:%M:%S') $tag rc=$rc $((SECONDS-t0))s" | tee -a "$VC/logs/queue.log"
exit $rc
