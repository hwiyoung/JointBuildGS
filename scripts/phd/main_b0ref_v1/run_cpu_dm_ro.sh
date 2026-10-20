#!/usr/bin/env bash
# PHD-MAIN-B0REF-v1: run one CPU step with the DIST71 task's mounts, ALL read-only (that task's payload too), plus /b0 and /docs of this
# task read-write (jointbuildgs:dev, network off, no GPU, nice 19, 8 GB).   bash run_cpu_dm_ro.sh <tag> <script.py> [args]
set -uo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd); ART=$(realpath "$REPO/../JointBuildGS-artifacts"); PH="$ART/phase-payloads/phd"
B0="$PH/main_b0ref_v1/PHD-MAIN-B0REF-v1"; DOCS="$REPO/docs/experiments/phd/main_b0ref_v1"
S1="$PH/main_stage1_v1/PHD-MAIN-STAGE1-v1"; S0="$PH/main_stage0_v1/PHD-MAIN-STAGE0-v1"; MT="$PH/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1"
MF="$PH/metrics_fix_v1/PHD-MAIN-METRICS-FIX-v1"; DIAG="$PH/main_stage1_diag_v1/PHD-MAIN-STAGE1-DIAG-v1"
DR="$PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1"; PREP="$PH/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1"
tag=$1; shift; script=$1; shift
mkdir -p "$B0/logs"; t0=$SECONDS
docker run --rm --name "jbgs-b0ref-${tag,,}" --network none --user "$(id -u):$(id -g)" --cpus 8 --memory 8g --shm-size 2g \
  -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl -e OMP_NUM_THREADS=8 -e CUDA_VISIBLE_DEVICES="" \
  -v "$PH:/ph:ro" -v "$S1:/out:ro" -v "$S0:/s0:ro" -v "$MT:/mt:ro" -v "$MF:/mf:ro" -v "$DR:/dr:ro" -v "$PREP:/prep:ro" -v "$DIAG:/diag:ro" \
  -v "$ART:/art:ro" -v "$REPO:/repo:ro" -v "$B0:/b0" -v "$DOCS:/docs" \
  -w /repo/scripts/phd/main_b0ref_v1 --entrypoint nice jointbuildgs:dev -n 19 python "$script" "$@" > "$B0/logs/$tag.log" 2>&1
rc=$?; echo "$(date '+%m-%d %H:%M:%S') $tag rc=$rc $((SECONDS-t0))s" | tee -a "$B0/logs/queue.log"; exit $rc
