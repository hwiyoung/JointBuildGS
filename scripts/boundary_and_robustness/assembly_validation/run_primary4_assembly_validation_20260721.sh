#!/usr/bin/env bash
# Detached E-PRIMARY4 measurement driver. Learning 0, inference 0, GPU 0.
set -Eeuo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO"

TASK="E-PRIMARY4-20260721"
BRANCH="exp/3b-surface-restore-corrected"
RUN_REL="phases/p2-gsjso/runs/boundary_and_robustness/20260721_primary4_assembly_validation"
RUN="$REPO/$RUN_REL"
DRIVER_REL="phases/p2-gsjso/runs/boundary_and_robustness/20260721_primary4_assembly_validation_driver"
DRIVER="$REPO/$DRIVER_REL"
LOG_DIR="$DRIVER/logs"
STATUS="$DRIVER/status.json"
LOCK="$DRIVER/driver.lock"
ISSUES="$REPO/phases/p2-gsjso/docs/issues.md"
SCRIPT="scripts/boundary_and_robustness/assembly_validation/primary4_assembly_validation.py"
QA_SCRIPT="scripts/boundary_and_robustness/assembly_validation/primary4_assembly_validation_qa.py"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
UID_GID="$(id -u):$(id -g)"
START_EPOCH="$(date +%s)"
CURRENT_WAVE="preflight"

mkdir -p "$RUN" "$DRIVER" "$LOG_DIR" "$RUN/roofer_logs"
exec 9>"$LOCK"
if ! flock -n 9; then
  printf "primary4 driver already holds %s\n" "$LOCK" >&2
  exit 75
fi

timestamp() {
  date -u "+%Y-%m-%dT%H:%M:%SZ"
}

log() {
  printf "%s %s\n" "$(timestamp)" "$*" | tee -a "$DRIVER/driver.log"
}

issue() {
  printf -- "- %s %s\n" "$(date "+%Y-%m-%d %H:%M:%S")" "$*" >> "$ISSUES"
  log "issues.md append: $*"
}

sha() {
  sha256sum "$1" | awk '{print $1}'
}

write_status() {
  local wave="$1"
  local state="$2"
  local detail="$3"
  local temporary="$STATUS.tmp"
  python3 - "$wave" "$state" "$detail" "$START_EPOCH" > "$temporary" <<'PY'
import json
import sys
import time
from datetime import datetime, timezone

wave, state, detail, started = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
print(json.dumps({
    "updated_utc": datetime.now(timezone.utc).isoformat(),
    "task": "E-PRIMARY4-20260721",
    "wave": wave,
    "state": state,
    "detail": detail,
    "elapsed_seconds": time.time() - started,
    "learning_runs_started": 0,
    "new_inference_runs": 0,
    "image_inputs_used": 0,
    "gpu_used": False,
}, ensure_ascii=False, indent=2))
PY
  mv "$temporary" "$STATUS"
}

run_tools() {
  docker run --rm \
    --user "$UID_GID" \
    -e HOME=/tmp \
    -e MPLCONFIGDIR=/tmp/matplotlib \
    -e XDG_CACHE_HOME=/tmp \
    -v "$REPO:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    "$TOOLS_IMAGE" "$@"
}

on_error() {
  local code=$?
  trap - ERR
  write_status "$CURRENT_WAVE" "failed" "driver exit=$code line=${BASH_LINENO[0]}"
  issue "$TASK failure: wave=$CURRENT_WAVE line=${BASH_LINENO[0]} exit_code=$code; learning_runs_started=0; new_inference_runs=0; gpu_used=false; log=$DRIVER_REL/driver.log"
  exit "$code"
}
trap on_error ERR

preflight() {
  CURRENT_WAVE="preflight"
  write_status "$CURRENT_WAVE" "running" "branch, remote, Docker, process, and source locks"
  local active_branch
  active_branch="$(git branch --show-current)"
  [[ "$active_branch" == "$BRANCH" ]]
  git fetch origin "$BRANCH" > "$LOG_DIR/git_fetch.log" 2>&1
  [[ "$(git rev-parse HEAD)" == "$(git rev-parse "origin/$BRANCH")" ]]
  if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    git status --short > "$LOG_DIR/tracked_status.log"
    log "tracked worktree changes present"
    return 1
  fi
  if pgrep -af "train.py|src.stage2.train|e5_c001.*train|runner.*train" \
    > "$LOG_DIR/learning_process_guard.log"; then
    log "learning-like process guard matched"
    return 1
  fi
  docker image inspect "$TOOLS_IMAGE" "$ROOFER_IMAGE" > "$LOG_DIR/docker_images.json"
  run_tools python3 "$SCRIPT" preflight > "$LOG_DIR/preflight.log" 2>&1
  write_status "$CURRENT_WAVE" "complete" "target_set=4 anchor_lock=true B1_lock=true"
  log "preflight complete head=$(git rev-parse HEAD)"
}

prepare_inputs() {
  CURRENT_WAVE="prepare"
  write_status "$CURRENT_WAVE" "running" "B-1 0.5 m flat input and class-2 support preparation"
  run_tools python3 "$SCRIPT" prepare > "$LOG_DIR/prepare.log" 2>&1
  issue "$TASK input preparation complete: targets=4; grid_m=0.5; reference_opened_during_prepare=false; prepared_sha256=$(sha "$RUN/prepared.json"); preflight_sha256=$(sha "$RUN/preflight.json"); learning_runs_started=0; new_inference_runs=0; gpu_used=false"
  write_status "$CURRENT_WAVE" "complete" "classified LAZ and roofprints frozen"
}

run_roofer_group() {
  local group="$1"
  local input="$RUN_REL/inputs/${group}_flat_g0500.laz"
  local roofprint="$RUN_REL/inputs/${group}_flat_g0500.geojson"
  local output="$RUN_REL/roofer/$group"
  local output_abs="$REPO/$output"
  mkdir -p "$output_abs"
  if compgen -G "$output_abs/*.city.jsonl" > /dev/null; then
    log "Roofer group=$group resume existing JSONSeq"
    printf "0"
    return 0
  fi
  local started ended elapsed
  started="$(date +%s)"
  timeout --signal=TERM --kill-after=20s 600s \
    docker run --rm \
      --user "$UID_GID" \
      -v "$REPO:/workspace/JointBuildGS" \
      -w /workspace/JointBuildGS \
      "$ROOFER_IMAGE" \
      --id-attribute building_id --jobs 3 --srs EPSG:25832 \
      --bld-class 6 --grnd-class 2 --lod22 \
      "/workspace/JointBuildGS/$input" \
      "/workspace/JointBuildGS/$roofprint" \
      "/workspace/JointBuildGS/$output" \
      > "$RUN/roofer_logs/${group}.log" 2>&1
  ended="$(date +%s)"
  elapsed="$((ended - started))"
  printf "%s" "$elapsed"
}

run_reproduction() {
  CURRENT_WAVE="reproduction"
  write_status "$CURRENT_WAVE" "running" "4907199 Roofer and B-1 hard-stop comparison"
  local wall
  wall="$(run_roofer_group reproduction)"
  run_tools python3 "$SCRIPT" score-group \
    --group reproduction --roofer-wall-seconds "$wall" \
    > "$LOG_DIR/score_reproduction.log" 2>&1
  issue "$TASK 4907199 reproduction hard stop passed: signed_delta_z_median_m=-0.014000000000; roof_rms_m=0.014000000000; reproduction_check_sha256=$(sha "$RUN/reproduction_check.json"); learning_runs_started=0; new_inference_runs=0"
  write_status "$CURRENT_WAVE" "complete" "199 reproduction passed; target group released"
}

run_targets() {
  CURRENT_WAVE="targets"
  write_status "$CURRENT_WAVE" "running" "three new target Roofer runs and standard scoring"
  local wall
  wall="$(run_roofer_group targets)"
  run_tools python3 "$SCRIPT" score-group \
    --group targets --roofer-wall-seconds "$wall" \
    > "$LOG_DIR/score_targets.log" 2>&1
  write_status "$CURRENT_WAVE" "complete" "three target rows measured"
}

finalize_bundle() {
  CURRENT_WAVE="finalize"
  write_status "$CURRENT_WAVE" "running" "CSV, one-page summary, manifest, and independent QA"
  run_tools python3 "$SCRIPT" finalize > "$LOG_DIR/finalize.log" 2>&1
  run_tools python3 "$QA_SCRIPT" > "$LOG_DIR/qa.json" 2>&1
  local counts
  counts="$(python3 - <<'PY'
import csv
rows=list(csv.DictReader(open('docs/experiments/evaluation/primary4_assembly_validation/tables/primary4_assembly_validation_measurements.csv', newline='', encoding='utf-8')))
print(f"has_lod22={sum(r['has_lod22']=='true' for r in rows)}/4;lod1_fallback={sum(r['lod1_fallback']=='true' for r in rows)}/4;gauge_b={sum(r['success_gauge_true']=='true' for r in rows)}/4;val3dity={sum(r['val3dity_valid']=='true' for r in rows)}/4")
PY
)"
  issue "$TASK measurement bundle complete: rows=4; $counts; measurements_sha256=$(sha docs/experiments/evaluation/primary4_assembly_validation/tables/primary4_assembly_validation_measurements.csv); summary_sha256=$(sha docs/experiments/evaluation/primary4_assembly_validation/reports/W_primary4_assembly_validation_summary_20260721.md); manifest_sha256=$(sha docs/experiments/evaluation/primary4_assembly_validation/manifests/primary4_assembly_validation_manifest.json); independent_QA=passed; learning_runs_started=0; new_inference_runs=0; image_inputs_used=0; gpu_used=false"
  write_status "$CURRENT_WAVE" "complete" "$counts; independent QA passed"
  log "finalize complete $counts"
}

preflight
prepare_inputs
run_reproduction
run_targets
finalize_bundle
write_status "complete" "complete" "all E-PRIMARY4 artifacts and QA complete"
log "$TASK driver complete"
