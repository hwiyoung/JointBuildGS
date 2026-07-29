#!/usr/bin/env bash
# Detached D-wave: fixed 178-building ALS degradation curve, learning/inference 0.
set -Eeuo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO"

BRANCH="exp/3b-surface-restore-corrected"
RUN_REL="phases/p2-gsjso/runs/20260721_degradation_curve"
RUN="$REPO/$RUN_REL"
RUNTIME="$RUN/runtime"
DRIVER_REL="phases/p2-gsjso/runs/20260721_degradation_curve_driver"
DRIVER="$REPO/$DRIVER_REL"
LOG_DIR="$DRIVER/logs"
STATUS="$DRIVER/status.json"
LOCK="$DRIVER/driver.lock"
ISSUES="$REPO/docs/issues.md"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
UID_GID="$(id -u):$(id -g)"
START_EPOCH="$(date +%s)"
CURRENT_WAVE="preflight"
PREP_COMMIT="$(git rev-parse HEAD)"
NOISE_COMMIT=""
FINAL_COMMIT=""
BATCH_TIMEOUT_SECONDS=1800
ISOLATED_TIMEOUT_SECONDS=120
ISOLATED_RETRY_TIMEOUT_SECONDS=600
RECOVERY_SCRIPT="scripts/experiments/degradation_curve/degradation_curve_v3_recovery.py"

mkdir -p "$RUN" "$RUNTIME" "$DRIVER" "$LOG_DIR"
exec 9>"$LOCK"
if ! flock -n 9; then
  printf "degradation-curve driver already holds %s\n" "$LOCK" >&2
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
    "task": "DC-V3",
    "wave": wave,
    "state": state,
    "detail": detail,
    "elapsed_seconds": time.time() - started,
    "learning_runs_started": 0,
    "new_inference_runs": 0,
    "image_inputs_used": 0,
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

push_retry() {
  local attempt
  for attempt in 1 2 3; do
    if git push origin "$BRANCH"; then
      log "push complete attempt=$attempt head=$(git rev-parse HEAD)"
      return 0
    fi
    log "push failed attempt=$attempt"
  done
  return 1
}

commit_paths() {
  local message="$1"
  shift
  local path
  for path in "$@"; do
    if [[ -e "$path" ]]; then
      git add -A -- "$path"
    fi
  done
  if git diff --cached --quiet; then
    log "no staged changes for $message"
    return 0
  fi
  git commit -m "$message"
  push_retry
}

on_error() {
  local code=$?
  trap - ERR
  write_status "$CURRENT_WAVE" "failed" "driver exit=$code line=${BASH_LINENO[0]}"
  issue "DC-V3 failure: wave=$CURRENT_WAVE line=${BASH_LINENO[0]} exit_code=$code; learning_runs_started=0; new_inference_runs=0; log=$DRIVER_REL/driver.log"
  git add -A -- docs/issues.md || true
  if ! git diff --cached --quiet; then
    git commit -m "DC-FAIL: record degradation-curve failure" || true
    push_retry || true
  fi
  exit "$code"
}
trap on_error ERR

preflight() {
  CURRENT_WAVE="preflight"
  write_status "$CURRENT_WAVE" "running" "branch, remote, source hashes, images, and learning guard"
  local active_branch
  active_branch="$(git branch --show-current)"
  if [[ "$active_branch" != "$BRANCH" ]]; then
    log "branch mismatch active=$active_branch expected=$BRANCH"
    return 1
  fi
  git fetch origin "$BRANCH" > "$LOG_DIR/git_fetch.log" 2>&1
  if [[ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$BRANCH")" ]]; then
    log "local/remote mismatch local=$(git rev-parse HEAD) remote=$(git rev-parse "origin/$BRANCH")"
    return 1
  fi
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
  docker image inspect "$TOOLS_IMAGE" "$ROOFER_IMAGE" \
    > "$LOG_DIR/docker_images.json"
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    verify-preflight > "$LOG_DIR/verify_preflight.log" 2>&1
  issue "DC-V3 preflight complete: population=178; stages=12; expected_rows=2136; roofer_image=$ROOFER_IMAGE; learning_runs_started=0; new_inference_runs=0"
  write_status "$CURRENT_WAVE" "complete" "population=178 stages=12 rows=2136"
}

build_base_and_zero() {
  CURRENT_WAVE="zero_stage"
  write_status "$CURRENT_WAVE" "running" "AOI crop, deterministic owner map, and accepted zero-stage score"
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    build-base > "$LOG_DIR/build_base.log" 2>&1
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    score-stage --stage baseline > "$LOG_DIR/score_baseline.log" 2>&1
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    validate-baseline > "$LOG_DIR/validate_baseline.log" 2>&1
  issue "DC-ZERO hard-stop complete: LoD2=178/178; RMS_median=0.421303923; pilot10=10/10; pilot_valid=9/10; pilot_RMS_median=0.337373145; pilot_face_ratio_median=1.875; pilot_completeness_median=0.999923703; all_metric_mismatch_count=0; accepted_artifact_reuse=true"
  write_status "$CURRENT_WAVE" "complete" "accepted zero stage matched all fixed rows"
}

stage_done() {
  local stage="$1"
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    verify-stage-measurement --stage "$stage" > /dev/null 2>&1
}

run_batch_roofer() {
  local stage="$1"
  local container_name="dc-v3-${stage//_/-}-batch"
  docker rm -f "$container_name" > /dev/null 2>&1 || true
  timeout --signal=TERM --kill-after=20s "${BATCH_TIMEOUT_SECONDS}s" \
    docker run --rm --name "$container_name" \
    --user "$UID_GID" \
    -v "$REPO:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    "$ROOFER_IMAGE" \
    --id-attribute building_id \
    --box 690791.740 5335864.050 691154.650 5336353.850 \
    "/workspace/JointBuildGS/$RUN_REL/runtime/input/$stage/aoi.laz" \
    /workspace/JointBuildGS/phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg \
    "/workspace/JointBuildGS/$RUN_REL/runtime/roofer/$stage" \
    > "$LOG_DIR/${stage}_roofer.log" 2>&1
  local code=$?
  docker rm -f "$container_name" > /dev/null 2>&1 || true
  return "$code"
}

run_isolated_attempt() {
  local stage="$1"
  local building_id="$2"
  local attempt="$3"
  local timeout_seconds="$4"
  local attempt_rel="$RUN_REL/runtime/recovery/$stage/work/$building_id/attempt_$attempt"
  local attempt_dir="$REPO/$attempt_rel/output"
  local log_rel="$DRIVER_REL/logs/recovery/$stage/${building_id}.attempt${attempt}.log"
  local log_path="$REPO/$log_rel"
  local container_name="dc-v3-${stage//_/-}-${building_id//_/-}-a$attempt"
  rm -rf "$REPO/$RUN_REL/runtime/recovery/$stage/work/$building_id/attempt_$attempt"
  mkdir -p "$attempt_dir" "$(dirname "$log_path")"
  docker rm -f "$container_name" > /dev/null 2>&1 || true
  local start end elapsed code
  start="$(date +%s)"
  if timeout --signal=TERM --kill-after=20s "${timeout_seconds}s" \
    docker run --rm --name "$container_name" \
      --user "$UID_GID" \
      -v "$REPO:/workspace/JointBuildGS" \
      -w /workspace/JointBuildGS \
      "$ROOFER_IMAGE" \
      --id-attribute building_id \
      --box 690791.740 5335864.050 691154.650 5336353.850 \
      --filter "building_id = '$building_id'" \
      "/workspace/JointBuildGS/$RUN_REL/runtime/input/$stage/aoi.laz" \
      /workspace/JointBuildGS/phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg \
      "/workspace/JointBuildGS/$attempt_rel/output" \
      > "$log_path" 2>&1; then
    code=0
  else
    code=$?
  fi
  end="$(date +%s)"
  elapsed="$((end - start))"
  docker rm -f "$container_name" > /dev/null 2>&1 || true
  if [[ "$code" -eq 0 ]]; then
    if run_tools python3 "$RECOVERY_SCRIPT" accept \
        --stage "$stage" \
        --building-id "$building_id" \
        --source-dir "$attempt_rel/output" \
        --wall-seconds "$elapsed" \
        --log-path "$log_rel" \
        --attempt "$attempt" \
        --timeout-seconds "$timeout_seconds" \
        > "$LOG_DIR/recovery/${stage}/${building_id}.accept.json"; then
      return 0
    else
      code=$?
    fi
  fi
  run_tools python3 "$RECOVERY_SCRIPT" record-failure \
    --stage "$stage" \
    --building-id "$building_id" \
    --exit-code "$code" \
    --wall-seconds "$elapsed" \
    --log-path "$log_rel" \
    --attempt "$attempt" \
    --timeout-seconds "$timeout_seconds" \
    > "$LOG_DIR/recovery/${stage}/${building_id}.failure${attempt}.json"
  return "$code"
}

run_stage_isolated() {
  local stage="$1"
  local stage_start="$2"
  run_tools python3 "$RECOVERY_SCRIPT" plan --stage "$stage" \
    > "$LOG_DIR/${stage}_recovery_plan.log" 2>&1
  local plan="$RUNTIME/recovery/$stage/plan.csv"
  local total completed building_id
  total="$(( $(wc -l < "$plan") - 1 ))"
  completed=0
  while IFS= read -r building_id; do
    if [[ -f "$RUNTIME/recovery/$stage/parts/$building_id.json" ]] \
      && [[ -f "$RUNTIME/roofer/$stage/$building_id.city.jsonl" ]] \
      && run_tools python3 "$RECOVERY_SCRIPT" part-ready \
        --stage "$stage" --building-id "$building_id" > /dev/null 2>&1; then
      completed="$((completed + 1))"
      write_status "$CURRENT_WAVE" "running" \
        "isolated recovery reused=$completed/$total building=$building_id"
      continue
    fi
    if ! run_isolated_attempt \
      "$stage" "$building_id" 1 "$ISOLATED_TIMEOUT_SECONDS"; then
      issue "DC-RECOVERY isolated retry: stage=$stage; building=$building_id; first_timeout_seconds=$ISOLATED_TIMEOUT_SECONDS; reconstruction_parameters_unchanged=true"
      if ! run_isolated_attempt \
        "$stage" "$building_id" 2 "$ISOLATED_RETRY_TIMEOUT_SECONDS"; then
        issue "DC-RECOVERY isolated failure: stage=$stage; building=$building_id; attempts=2; learning_runs_started=0; new_inference_runs=0"
        return 1
      fi
    fi
    completed="$((completed + 1))"
    write_status "$CURRENT_WAVE" "running" \
      "isolated recovery completed=$completed/$total building=$building_id"
  done < <(tail -n +2 "$plan" | cut -d, -f3)
  run_tools python3 "$RECOVERY_SCRIPT" finalize --stage "$stage" \
    > "$LOG_DIR/${stage}_recovery_finalize.log" 2>&1
  local end elapsed
  end="$(date +%s)"
  elapsed="$((end - stage_start))"
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    record-roofer --stage "$stage" --wall-seconds "$elapsed" \
    > "$LOG_DIR/${stage}_record.log" 2>&1
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    score-stage --stage "$stage" > "$LOG_DIR/${stage}_score.log" 2>&1
  issue "DC-STAGE isolated recovery complete: stage=$stage; rows=178; measurement_sha256=$(sha "$RUNTIME/stage_measurements/$stage.csv"); recovery_manifest_sha256=$(sha "$RUNTIME/recovery/$stage/manifest.json"); wall_seconds=$elapsed; reconstruction_parameter_change_count=0; learning_runs_started=0; new_inference_runs=0"
  write_status "$CURRENT_WAVE" "complete" \
    "rows=178 execution=isolated_per_building wall_seconds=$elapsed"
}

run_stage() {
  local stage="$1"
  CURRENT_WAVE="$stage"
  if stage_done "$stage"; then
    issue "DC-STAGE reused verified pre-driver measurement: stage=$stage; rows=178; measurement_sha256=$(sha "$RUNTIME/stage_measurements/$stage.csv"); learning_runs_started=0; new_inference_runs=0"
    write_status "$CURRENT_WAVE" "complete" "reused verified 178-row stage measurement"
    return 0
  fi
  write_status "$CURRENT_WAVE" "running" "generate input, Roofer default, val3dity, canonical scoring"
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    make-stage --stage "$stage" > "$LOG_DIR/${stage}_input.log" 2>&1
  local start end elapsed batch_code
  start="$(date +%s)"
  if [[ -f "$RUNTIME/recovery/$stage/plan.csv" ]]; then
    issue "DC-RECOVERY resume isolated stage: stage=$stage; accepted_parts=$(find "$RUNTIME/roofer/$stage" -maxdepth 1 -name '*.city.jsonl' 2>/dev/null | wc -l); reconstruction_parameters_unchanged=true"
    mkdir -p "$RUNTIME/roofer/$stage"
    run_stage_isolated "$stage" "$start"
    return 0
  fi
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    clean-stage-output --stage "$stage"
  if [[ "$stage" == "noise_sigma_0p80" ]]; then
    issue "DC-RECOVERY start isolated stage: stage=$stage; reason=prior_batch_stalled_14h41m; per_building_timeout_seconds=$ISOLATED_TIMEOUT_SECONDS; retry_timeout_seconds=$ISOLATED_RETRY_TIMEOUT_SECONDS; reconstruction_parameters_unchanged=true"
    run_stage_isolated "$stage" "$start"
    return 0
  fi
  if run_batch_roofer "$stage"; then
    batch_code=0
  else
    batch_code=$?
  fi
  if [[ "$batch_code" -ne 0 ]]; then
    issue "DC-RECOVERY batch fallback: stage=$stage; exit_code=$batch_code; batch_timeout_seconds=$BATCH_TIMEOUT_SECONDS; execution=isolated_per_building_same_parameters"
    run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
      clean-stage-output --stage "$stage"
    run_stage_isolated "$stage" "$start"
    return 0
  fi
  end="$(date +%s)"
  elapsed="$((end - start))"
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    record-roofer --stage "$stage" --wall-seconds "$elapsed" \
    > "$LOG_DIR/${stage}_record.log" 2>&1
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    score-stage --stage "$stage" > "$LOG_DIR/${stage}_score.log" 2>&1
  issue "DC-STAGE complete: stage=$stage; rows=178; measurement_sha256=$(sha "$RUNTIME/stage_measurements/$stage.csv"); roofer_wall_seconds=$elapsed; batch_timeout_seconds=$BATCH_TIMEOUT_SECONDS; learning_runs_started=0; new_inference_runs=0"
  write_status "$CURRENT_WAVE" "complete" "rows=178 roofer_wall_seconds=$elapsed"
}

finalize_noise() {
  CURRENT_WAVE="noise_finalize"
  write_status "$CURRENT_WAVE" "running" "aggregate baseline plus five noise stages"
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    finalize --scope noise > "$LOG_DIR/noise_finalize.log" 2>&1
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3_qa.py \
    --scope noise > "$LOG_DIR/noise_qa.log" 2>&1
  issue "DC-NOISE partial complete: stages=6/12; rows=1068/2136; measurements_sha256=$(sha docs/experiments/degradation_curve/tables/degradation_curve_measurements.csv); summary_sha256=$(sha docs/experiments/degradation_curve/tables/degradation_curve_summary.csv); manifest_sha256=$(sha docs/experiments/degradation_curve/manifests/degradation_curve_manifest.json); noise_figure_sha256=$(sha docs/figs/degradation_curve/degradation_curve_noise.png); learning_runs_started=0; new_inference_runs=0"
  commit_paths \
    "DC-NOISE: measure canonical noise axis" \
    docs/issues.md \
    docs/experiments/degradation_curve/tables/degradation_curve_measurements.csv \
    docs/experiments/degradation_curve/tables/degradation_curve_summary.csv \
    docs/experiments/degradation_curve/manifests/degradation_curve_manifest.json \
    docs/experiments/degradation_curve/reports/W_degradation_curve_summary_20260721.md \
    docs/figs/degradation_curve/degradation_curve_noise.png \
    "$RUN_REL/zero_stage_validation.json"
  NOISE_COMMIT="$(git rev-parse HEAD)"
  write_status "$CURRENT_WAVE" "complete" "commit=$NOISE_COMMIT rows=1068"
}

finalize_full() {
  CURRENT_WAVE="full_finalize"
  write_status "$CURRENT_WAVE" "running" "aggregate all twelve stages and validate"
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3.py \
    finalize --scope full > "$LOG_DIR/full_finalize.log" 2>&1
  run_tools python3 scripts/experiments/degradation_curve/degradation_curve_v3_qa.py \
    --scope full > "$LOG_DIR/full_qa.log" 2>&1
  issue "DC-FULL measurement complete: stages=12/12; rows=2136; measurements_sha256=$(sha docs/experiments/degradation_curve/tables/degradation_curve_measurements.csv); summary_sha256=$(sha docs/experiments/degradation_curve/tables/degradation_curve_summary.csv); manifest_sha256=$(sha docs/experiments/degradation_curve/manifests/degradation_curve_manifest.json); noise_figure_sha256=$(sha docs/figs/degradation_curve/degradation_curve_noise.png); density_figure_sha256=$(sha docs/figs/degradation_curve/degradation_curve_density.png); one_page_sha256=$(sha docs/experiments/degradation_curve/reports/W_degradation_curve_summary_20260721.md); learning_runs_started=0; new_inference_runs=0"
  commit_paths \
    "DC-FULL: measure 178-building degradation curve" \
    docs/issues.md \
    docs/experiments/degradation_curve/tables/degradation_curve_measurements.csv \
    docs/experiments/degradation_curve/tables/degradation_curve_summary.csv \
    docs/experiments/degradation_curve/manifests/degradation_curve_manifest.json \
    docs/experiments/degradation_curve/reports/W_degradation_curve_summary_20260721.md \
    docs/figs/degradation_curve/degradation_curve_noise.png \
    docs/figs/degradation_curve/degradation_curve_density.png \
    "$RUN_REL/zero_stage_validation.json"
  FINAL_COMMIT="$(git rev-parse HEAD)"
  write_status "$CURRENT_WAVE" "complete" "commit=$FINAL_COMMIT rows=2136"
}

finalize_ledger() {
  CURRENT_WAVE="ledger"
  issue "DC-LEDGER commits: prep=$PREP_COMMIT; noise=$NOISE_COMMIT; full=$FINAL_COMMIT; manifest_sha256=$(sha docs/experiments/degradation_curve/manifests/degradation_curve_manifest.json); issues_sha256_before_ledger_commit=$(sha docs/issues.md)"
  commit_paths \
    "DC-LEDGER: record degradation-curve commits" \
    docs/issues.md
  local ledger_commit
  ledger_commit="$(git rev-parse HEAD)"
  write_status "$CURRENT_WAVE" "complete" "ledger_commit=$ledger_commit"
  log "complete prep=$PREP_COMMIT noise=$NOISE_COMMIT full=$FINAL_COMMIT ledger=$ledger_commit"
}

main() {
  log "start head=$PREP_COMMIT branch=$(git branch --show-current)"
  preflight
  build_base_and_zero
  for stage in \
    noise_sigma_0p05 \
    noise_sigma_0p10 \
    noise_sigma_0p20 \
    noise_sigma_0p40 \
    noise_sigma_0p80; do
    run_stage "$stage"
  done
  finalize_noise
  for stage in \
    density_retain_1of2 \
    density_retain_1of4 \
    density_retain_1of10 \
    density_retain_1of20 \
    combo_sigma_0p20_retain_1of4 \
    combo_sigma_0p40_retain_1of10; do
    run_stage "$stage"
  done
  finalize_full
  finalize_ledger
  write_status "complete" "complete" "all 12 stages, 2136 rows, commits pushed"
}

main "$@"
