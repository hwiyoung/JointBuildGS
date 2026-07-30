#!/usr/bin/env bash
# Detached learning-zero same-block anchor-census supplement driver.
# Launch from repository root:
#   mkdir -p phases/p2-gsjso/runs/boundary_and_robustness/20260720_anchor_census_supplement_driver
#   setsid nohup bash \
#     scripts/boundary_and_robustness/boundary_map/run_anchor_census_supplement_20260720.sh \
#     > phases/p2-gsjso/runs/boundary_and_robustness/20260720_anchor_census_supplement_driver/detached.log \
#     2>&1 < /dev/null &
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO" || exit 1

BRANCH="exp/3b-surface-restore-corrected"
SCRIPT="scripts/boundary_and_robustness/boundary_map/anchor_census_supplement.py"
RUN_REL="phases/p2-gsjso/runs/boundary_and_robustness/20260720_anchor_census_supplement"
RUN="$REPO/$RUN_REL"
DRIVER_REL="phases/p2-gsjso/runs/boundary_and_robustness/20260720_anchor_census_supplement_driver"
DRIVER="$REPO/$DRIVER_REL"
LOG_DIR="$DRIVER/logs"
STATUS="$DRIVER/status.json"
STATE="$DRIVER/driver_state.json"
LOCK_FILE="$DRIVER/driver.lock"
PID_FILE="$DRIVER/launcher.pid"
ISSUES="$REPO/phases/p2-gsjso/docs/issues.md"

RUN_PAIRS="$RUN_REL/anchor_census_supplement_pairs.csv"
RUN_MEASUREMENTS="$RUN_REL/anchor_census_supplement_measurements.csv"
RUN_RELIABILITY="$RUN_REL/anchor_census_supplement_same_block_reliability_pairs.csv"
RUN_MANIFEST="$RUN_REL/anchor_census_supplement_measure_manifest.json"
DOC_PAIRS="docs/experiments/input-and-alignment/boundary_map/tables/anchor_census_supplement_pairs.csv"
DOC_MEASUREMENTS="docs/experiments/input-and-alignment/boundary_map/tables/anchor_census_supplement_measurements.csv"
DOC_RELIABILITY="docs/experiments/input-and-alignment/boundary_map/tables/anchor_census_supplement_same_block_reliability_pairs.csv"
LADDER="docs/experiments/input-and-alignment/boundary_map/tables/boundary_map_v4_1_ladder.csv"
PUBLIC_MANIFEST="docs/experiments/input-and-alignment/boundary_map/manifests/anchor_census_supplement_manifest.json"
SUMMARY="docs/experiments/input-and-alignment/boundary_map/reports/W_anchor_census_supplement_boundary_map_v4_1_summary_20260720.md"

DEV_IMAGE="jointbuildgs:dev"
DEV_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
ALLOWLIST="supplement_FM_dense_dial_2px_same_block"
UID_GID="$(id -u):$(id -g)"
START_EPOCH="$(date +%s)"
LOCK_ACQUIRED=0
CURRENT_STAGE="start"
MEASUREMENT_COMMIT=""
PUBLIC_COMMIT=""

mkdir -p "$LOG_DIR" "$RUN"

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
  if [[ -f "$1" ]]; then
    sha256sum "$1" | awk '{print $1}'
  else
    printf "missing"
  fi
}

write_state_files() {
  local stage="$1"
  local state="$2"
  local detail="$3"
  local elapsed=$(( $(date +%s) - START_EPOCH ))
  local temporary="$STATUS.tmp"
  printf '{\n  "updated_utc": "%s",\n  "task": "anchor census supplement boundary_map_v4_1",\n  "stage": "%s",\n  "state": "%s",\n  "detail": "%s",\n  "elapsed_seconds": %s,\n  "gpu_used": false,\n  "gpu_budget_seconds": 600,\n  "new_mast3r_inference_runs": 0,\n  "learning_runs_started": 0,\n  "new_inference_allowlist": "%s"\n}\n' \
    "$(timestamp)" "$stage" "$state" "$detail" "$elapsed" "$ALLOWLIST" \
    > "$temporary"
  mv "$temporary" "$STATUS"
  cp "$STATUS" "$STATE"
}

run_dev() {
  docker run --rm -i \
    --user "$UID_GID" \
    -e HOME=/tmp \
    -e PYTHONPYCACHEPREFIX=/tmp/pycache \
    -e MPLCONFIGDIR=/tmp/matplotlib \
    -e XDG_CACHE_HOME=/tmp \
    -v "$REPO:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    "$DEV_IMAGE" "$@"
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

commit_stage() {
  local message="$1"
  shift
  git add -- "$@"
  if git diff --cached --quiet; then
    log "no staged changes for $message"
  else
    git commit -m "$message" || return 1
  fi
  push_retry
}

partial_commit() {
  git add -- \
    phases/p2-gsjso/docs/issues.md \
    "$RUN_REL" \
    "$DOC_PAIRS" \
    "$DOC_MEASUREMENTS" \
    "$DOC_RELIABILITY" \
    "$LADDER" \
    "$PUBLIC_MANIFEST" \
    "$SUMMARY" 2>/dev/null || true
  if ! git diff --cached --quiet; then
    git commit -m "ACS-PARTIAL: retain supplement stage $CURRENT_STAGE" || true
    push_retry || true
  fi
}

cleanup() {
  local rc="$?"
  trap - EXIT
  if (( rc != 0 )); then
    issue "ACS failure: stage=$CURRENT_STAGE rc=$rc; retained outputs are partial; new_mast3r_inference_runs=0; learning_runs_started=0."
    partial_commit
    write_state_files "$CURRENT_STAGE" "failed" "exit_code=$rc"
  fi
  if (( LOCK_ACQUIRED == 1 )); then
    rm -f "$PID_FILE"
  fi
  exit "$rc"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

preflight() {
  CURRENT_STAGE="preflight"
  write_state_files "$CURRENT_STAGE" "running" "checking fixed scope and caches"
  if [[ "$(git branch --show-current)" != "$BRANCH" ]]; then
    log "preflight failed: branch drift"
    return 1
  fi
  if [[ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$BRANCH")" ]]; then
    log "preflight failed: local HEAD differs from origin branch"
    return 1
  fi
  if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    log "preflight failed: tracked worktree is dirty"
    return 1
  fi
  local unexpected_untracked
  unexpected_untracked="$(
    git -c core.quotePath=false status --porcelain --untracked-files=all |
      awk '$1=="??"{print substr($0,4)}' |
      grep -Fvx 'docs/W_밤샘3과제_검수_20260717.md' |
      grep -Fvx 'docs/사전등록서_품질축본선_초안v1.2_20260718.md' || true
  )"
  if [[ -n "$unexpected_untracked" ]]; then
    log "preflight failed: unexpected untracked paths: $unexpected_untracked"
    return 1
  fi
  if [[ "$(docker image inspect "$DEV_IMAGE" --format '{{.Id}}')" != "$DEV_IMAGE_ID" ]]; then
    log "preflight failed: dev image ID drift"
    return 1
  fi
  if ps -eo cmd | grep -E \
    'train(_|\.py| )|run_training|gsjso.*optim|torchrun.*train' |
    grep -v -E 'grep -E|run_anchor_census_supplement' >/dev/null; then
    log "preflight failed: learning-like process detected"
    return 1
  fi
  run_dev python3 -m py_compile "$SCRIPT" \
    > "$LOG_DIR/python_compile.log" 2>&1 || return 1
  run_dev python3 "$SCRIPT" preflight \
    > "$LOG_DIR/preflight.log" 2>&1 || return 1
  write_state_files "$CURRENT_STAGE" "complete" "9 targets, 90 caches, GPU not required"
  log "preflight complete head=$(git rev-parse HEAD)"
}

measure_stage() {
  CURRENT_STAGE="S-2"
  write_state_files "$CURRENT_STAGE" "running" "cache-only same-block re-pooling"
  run_dev python3 "$SCRIPT" measure \
    > "$LOG_DIR/measure.log" 2>&1 || return 1
  run_dev python3 "$SCRIPT" qa-measure \
    > "$LOG_DIR/qa_measure.log" 2>&1 || return 1
  issue "ACS-S2 same-block re-pooling recorded: targets=9; target_pairs=90; reproduction_rows=1; reliability_pairs=24; measurements_sha256=$(sha "$DOC_MEASUREMENTS"); pairs_sha256=$(sha "$DOC_PAIRS"); reliability_sha256=$(sha "$DOC_RELIABILITY"); measure_manifest_sha256=$(sha "$RUN_MANIFEST"); target_cache_reuse_runs=90; reproduction_cache_reuse_runs=10; new_mast3r_inference_runs=0; gpu_used=false; learning_runs_started=0; allowlist=$ALLOWLIST."
  commit_stage \
    "ACS-S2: repool nine same-block anchor targets" \
    phases/p2-gsjso/docs/issues.md \
    "$RUN_REL" \
    "$DOC_PAIRS" \
    "$DOC_MEASUREMENTS" \
    "$DOC_RELIABILITY" || return 1
  MEASUREMENT_COMMIT="$(git rev-parse HEAD)"
  write_state_files "$CURRENT_STAGE" "complete" "commit=$MEASUREMENT_COMMIT"
}

finalize_stage() {
  CURRENT_STAGE="S-4"
  write_state_files "$CURRENT_STAGE" "running" "boundary_map_v4_1 and summary"
  run_dev python3 "$SCRIPT" finalize \
    > "$LOG_DIR/finalize.log" 2>&1 || return 1
  run_dev python3 "$SCRIPT" qa \
    > "$LOG_DIR/qa_public.log" 2>&1 || return 1
  local counts
  counts="$(
    run_dev python3 -c \
      "import json; p=json.load(open('$PUBLIC_MANIFEST')); print('/'.join(str(p['cell_counts'][k]) for k in ['cell_1_assembled','cell_2_anchored','cell_3_outline_only','cell_4_beyond_image']))" |
      tail -n 1
  )"
  issue "ACS-S4 boundary_map_v4_1 recorded: cells_1_2_3_4=$counts; ladder_sha256=$(sha "$LADDER"); summary_sha256=$(sha "$SUMMARY"); public_manifest_sha256=$(sha "$PUBLIC_MANIFEST"); non_target_old_fields_identical=169; map_regenerated=false; new_mast3r_inference_runs=0; learning_runs_started=0."
  commit_stage \
    "ACS-S4: publish boundary-map-v4.1 supplement" \
    phases/p2-gsjso/docs/issues.md \
    "$LADDER" \
    "$PUBLIC_MANIFEST" \
    "$SUMMARY" || return 1
  PUBLIC_COMMIT="$(git rev-parse HEAD)"
  write_state_files "$CURRENT_STAGE" "complete" "commit=$PUBLIC_COMMIT"
}

ledger_stage() {
  CURRENT_STAGE="ledger"
  issue "ACS-20260720 commit ledger: prep_commit=$(git log --format=%H --grep='ACS-PREP:' -1); measurement_commit=$MEASUREMENT_COMMIT; public_commit=$PUBLIC_COMMIT; issues.md included in each synchronized artifact commit; new_mast3r_inference_runs=0; learning_runs_started=0; allowlist=$ALLOWLIST."
  commit_stage \
    "ACS-LEDGER: record supplement commits" \
    phases/p2-gsjso/docs/issues.md || return 1
  write_state_files "complete" "complete" "head=$(git rev-parse HEAD)"
  log "anchor census supplement complete head=$(git rev-parse HEAD)"
}

main() {
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    log "another supplement driver holds the lock"
    return 73
  fi
  LOCK_ACQUIRED=1
  printf "%s\n" "$$" > "$PID_FILE"
  write_state_files "start" "running" "detached driver entered"
  preflight || return 1
  measure_stage || return 1
  finalize_stage || return 1
  ledger_stage || return 1
}

main "$@"
