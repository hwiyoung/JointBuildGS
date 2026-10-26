#!/usr/bin/env bash
# Same read-only aliases as AXES71; all new payloads belong to LOSSTRAIN /lt.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
ART=$(realpath "$REPO/../JointBuildGS-artifacts")
PH="$ART/phase-payloads/phd"
LT="$PH/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1"
tag=$1; shift
log="$LT/logs/axes_${tag}_$(date +%Y%m%dT%H%M%S).log"
set +e
docker run --rm --name "jbgs-lt-axes-${tag,,}" --network none --user "$(id -u):$(id -g)" \
  --cpus 8 --memory 24g --shm-size 4g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS=8 -e TZ=Asia/Seoul \
  -v "$PH:/ph:ro" -v "$LT:/lt" -v "$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1:/out:ro" \
  -v "$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1:/s0:ro" -v "$PH/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1:/mt:ro" \
  -v "$PH/metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1:/mf:ro" -v "$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1:/dr:ro" \
  -v "$PH/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1:/prep:ro" -v "$PH/main_stage1_diag_v1/PHD-MAIN-STAGE1-DIAG-v1:/diag:ro" \
  -v "$ART:/art:ro" -v "$REPO:/repo:ro" -v "$REPO/docs/experiments/phd/main_losstrain_v1:/docs" \
  -w /repo/scripts/phd/main_losstrain_v1 --entrypoint python jointbuildgs:dev "$@" > "$log" 2>&1
rc=$?
cat "$log"
exit "$rc"
