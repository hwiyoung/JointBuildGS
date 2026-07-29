#!/usr/bin/env bash
# Detached learning-zero anchor-census driver.
# Launch from the repository root:
#   mkdir -p phases/p2-gsjso/runs/20260720_anchor_census_driver
#   setsid nohup bash scripts/experiments/boundary_map/run_anchor_census_20260720.sh \
#     > phases/p2-gsjso/runs/20260720_anchor_census_driver/detached.log \
#     2>&1 < /dev/null &
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO" || exit 1

BRANCH="exp/3b-surface-restore-corrected"
RUN_REL="phases/p2-gsjso/runs/20260720_anchor_census"
RUN="$REPO/$RUN_REL"
DRIVER_REL="phases/p2-gsjso/runs/20260720_anchor_census_driver"
DRIVER="$REPO/$DRIVER_REL"
LOG_DIR="$DRIVER/logs"
STATUS="$DRIVER/status.json"
STATE="$DRIVER/driver_state.json"
LOCK_FILE="$DRIVER/driver.lock"
PID_FILE="$DRIVER/launcher.pid"
CID_FILE="$DRIVER/fm_container.cid"
ISSUES="$REPO/docs/issues.md"

SCRIPT="scripts/experiments/boundary_map/anchor_census.py"
DENSE_SCRIPT="scripts/experiments/boundary_map/anchor_census_dense.py"
JOBS="$RUN_REL/anchor_census_jobs.json"
PREP_MANIFEST="$RUN_REL/anchor_census_prepare_manifest.json"
INFERENCE_CSV="$RUN_REL/anchor_census_inference_measurements.csv"
INFERENCE_PAIRS="$RUN_REL/anchor_census_pairs.csv"
INFERENCE_PROGRESS="$RUN_REL/anchor_census_progress.json"
INFERENCE_MANIFEST="$RUN_REL/anchor_census_inference_manifest.json"
MEASUREMENTS="$RUN_REL/anchor_census_measurements.csv"
RUN_MANIFEST="$RUN_REL/anchor_census_manifest.json"
PREREG="docs/사전등록서_품질축본선_잠금후보v1.5_20260720.md"

DEV_IMAGE="jointbuildgs:dev"
DEV_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
MAST3R_IMAGE="jointbuildgs-s3ap-mast3r:20260714-f5209af"
MAST3R_IMAGE_ID="sha256:89d64b4c7112cc55db0d42d562e2a0208858658c0c67ab1bd48424175c50f501"
FM_CONTAINER_NAME="jointbuildgs-anchor-census-20260720"
MODEL_REVISION="06e7259f34c3060f322df5cb0c7b9094f57e41fc"
MODEL_SHA256="0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
MODEL_CONFIG_SHA256="718eb93dc4f9e4332b60cc0041af962d712cbd346d7770ce35c5b22cff68eae4"
MODEL_REPO_HOST="/home/innopam/.cache/huggingface/hub/models--naver--MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric"
MODEL_HOST="$MODEL_REPO_HOST/snapshots/$MODEL_REVISION"
MODEL_REPO_CONTAINER="/models/mast3r_metric"
MODEL_CONTAINER="$MODEL_REPO_CONTAINER/snapshots/$MODEL_REVISION"
ALLOWLIST="census_FM_dense_dial_2px_only"
FM_BUDGET_SECONDS=21600
FM_FINALIZE_GRACE_SECONDS=120
UID_GID="$(id -u):$(id -g)"
START_EPOCH="$(date +%s)"

MEASUREMENT_COMMIT=""
PUBLIC_COMMIT=""
LOCK_ACQUIRED=0

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

write_status() {
  local stage="$1"
  local state="$2"
  local detail="$3"
  local temporary="$STATUS.tmp"
  python3 - "$stage" "$state" "$detail" "$START_EPOCH" > "$temporary" <<'PY'
import json
import sys
import time
from datetime import datetime, timezone

stage, state, detail, started = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
print(json.dumps({
    "updated_utc": datetime.now(timezone.utc).isoformat(),
    "task": "anchor census boundary_map_v4",
    "stage": stage,
    "state": state,
    "detail": detail,
    "elapsed_seconds": time.time() - started,
    "learning_runs_started": 0,
    "allowed_new_inference": "census_FM_dense_dial_2px_only",
    "gpu_budget_seconds": 21600,
}, ensure_ascii=False, indent=2))
PY
  mv "$temporary" "$STATUS"
}

write_state() {
  local stage="$1"
  local state="$2"
  local detail="$3"
  local temporary="$STATE.tmp"
  python3 - "$stage" "$state" "$detail" > "$temporary" <<'PY'
import json
import sys
from datetime import datetime, timezone

print(json.dumps({
    "updated_utc": datetime.now(timezone.utc).isoformat(),
    "stage": sys.argv[1],
    "state": sys.argv[2],
    "detail": sys.argv[3],
    "learning_runs_started": 0,
    "allowed_new_inference": ["census_FM_dense_dial_2px_only"],
}, ensure_ascii=False, indent=2))
PY
  mv "$temporary" "$STATE"
}

cleanup_fm_container() {
  local cid=""
  if [[ -s "$CID_FILE" ]]; then
    cid="$(head -n 1 "$CID_FILE")"
  fi
  if [[ -n "$cid" ]]; then
    docker stop --time 20 "$cid" >/dev/null 2>&1 || true
    docker rm -f "$cid" >/dev/null 2>&1 || true
  fi
  docker rm -f "$FM_CONTAINER_NAME" >/dev/null 2>&1 || true
  rm -f "$CID_FILE"
}

cleanup_driver() {
  local rc="$?"
  trap - EXIT
  if (( LOCK_ACQUIRED == 1 )); then
    cleanup_fm_container
    rm -f "$PID_FILE"
  fi
  exit "$rc"
}

trap cleanup_driver EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

run_dev() {
  docker run --rm -i \
    --user "$UID_GID" \
    -e HOME=/tmp \
    -e MPLCONFIGDIR=/tmp/matplotlib \
    -e XDG_CACHE_HOME=/tmp \
    -v "$REPO:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    "$DEV_IMAGE" "$@"
}

run_mast3r() {
  local inner_seconds=$(( FM_BUDGET_SECONDS - FM_FINALIZE_GRACE_SECONDS ))
  cleanup_fm_container
  timeout --signal=TERM --kill-after=60s "${FM_BUDGET_SECONDS}s" \
    docker run --rm \
      --name "$FM_CONTAINER_NAME" \
      --cidfile "$CID_FILE" \
      --stop-timeout 30 \
      --user "$UID_GID" \
      --gpus device=0 \
      -e HOME=/tmp \
      -e MPLCONFIGDIR=/tmp/matplotlib \
      -e XDG_CACHE_HOME=/tmp \
      -e MAST3R_DOCKER_IMAGE_ID="$MAST3R_IMAGE_ID" \
      -v "$REPO:/workspace/JointBuildGS" \
      -v "$MODEL_REPO_HOST:$MODEL_REPO_CONTAINER:ro" \
      -w /workspace/JointBuildGS \
      "$MAST3R_IMAGE" \
      python3 "$DENSE_SCRIPT" \
        --model-dir "$MODEL_CONTAINER" \
        --device cuda:0 \
        --max-seconds "$inner_seconds" \
        --jobs "$JOBS"
  local rc="$?"
  cleanup_fm_container
  return "$rc"
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
  push_retry || return 1
}

preflight() {
  write_status "preflight" "running" "checking committed gate and locked runtime"
  write_state "preflight" "running" "start gates"
  if [[ "$(git branch --show-current)" != "$BRANCH" ]]; then
    log "preflight failed: branch drift"
    return 1
  fi
  if [[ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$BRANCH")" ]]; then
    log "preflight failed: local HEAD differs from origin branch"
    return 1
  fi
  if ! git cat-file -e "HEAD:$PREREG"; then
    log "preflight failed: v1.5 prereg is not committed"
    return 1
  fi
  local tracked_dirty
  tracked_dirty="$(git status --porcelain --untracked-files=no)"
  if [[ -n "$tracked_dirty" ]]; then
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
  if [[ "$(docker image inspect "$MAST3R_IMAGE" --format '{{.Id}}')" != "$MAST3R_IMAGE_ID" ]]; then
    log "preflight failed: MASt3R image ID drift"
    return 1
  fi
  if [[ ! -f "$MODEL_HOST/model.safetensors" || ! -f "$MODEL_HOST/config.json" ]]; then
    log "preflight failed: model snapshot missing"
    return 1
  fi
  if [[ "$(sha256sum "$MODEL_HOST/model.safetensors" | awk '{print $1}')" != "$MODEL_SHA256" ]]; then
    log "preflight failed: model SHA drift"
    return 1
  fi
  if [[ "$(sha256sum "$MODEL_HOST/config.json" | awk '{print $1}')" != "$MODEL_CONFIG_SHA256" ]]; then
    log "preflight failed: model config SHA drift"
    return 1
  fi
  if ps -eo cmd | grep -E \
    'train(_|\\.py| )|run_training|gsjso.*optim|torchrun.*train' |
    grep -v -E 'grep -E|run_anchor_census' >/dev/null; then
    log "preflight failed: learning-like process detected"
    return 1
  fi
  if ! run_dev python3 -m py_compile "$SCRIPT" "$DENSE_SCRIPT" \
    > "$LOG_DIR/python_compile.log" 2>&1; then
    log "preflight failed: Python compile"
    return 1
  fi
  if ! run_dev python3 - "$JOBS" "$PREP_MANIFEST" <<'PY' \
    > "$LOG_DIR/prep_qa.log" 2>&1
import hashlib
import json
import sys
from pathlib import Path

jobs_path = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
assert len(jobs["jobs"]) == 58
assert [job["priority_rank"] for job in jobs["jobs"]] == list(range(1, 59))
assert all(len(job["pairs"]) == 10 for job in jobs["jobs"])
assert jobs["model"]["learning_runs_started"] == 0
assert jobs["model"]["new_inference_type"] == "census_FM_dense_dial_2px_only"
assert manifest["set_validation"]["derived_equals_fixed"] is True
assert manifest["derivation"]["arithmetic_check"] == "64-6=58; 43+15=58"
actual = hashlib.sha256(jobs_path.read_bytes()).hexdigest()
assert actual == manifest["jobs_sha256"]
print({"jobs": 58, "pairs": 580, "learning_runs_started": 0})
PY
  then
    log "preflight failed: prepared census bundle QA"
    return 1
  fi
  if ! docker run --rm --gpus device=0 "$MAST3R_IMAGE" \
    nvidia-smi --query-gpu=name --format=csv,noheader \
    > "$LOG_DIR/gpu_preflight.log" 2>&1; then
    log "preflight failed: GPU container"
    return 1
  fi
  write_status "preflight" "complete" "all gates passed"
  write_state "preflight" "complete" "all gates passed"
  log "preflight complete head=$(git rev-parse HEAD)"
}

measurement_qa() {
  run_dev python3 - "$INFERENCE_CSV" "$INFERENCE_PAIRS" \
    "$INFERENCE_MANIFEST" > "$LOG_DIR/measurement_qa.log" 2>&1 <<'PY'
import csv
import json
import sys
from pathlib import Path

csv_path, pairs_path, manifest_path = map(Path, sys.argv[1:])
rows = list(csv.DictReader(csv_path.open(newline="", encoding="utf-8")))
pairs = list(csv.DictReader(pairs_path.open(newline="", encoding="utf-8")))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
assert len(rows) == 58
assert len({row["building_id"] for row in rows}) == 58
assert [int(row["priority_rank"]) for row in rows] == list(range(1, 59))
assert all(row["learning_runs_started"] == "0" for row in rows)
assert all(
    row["new_inference_type"] == "census_FM_dense_dial_2px_only"
    for row in rows
)
assert len(pairs) == 580
assert all(row["learning_runs_started"] == "0" for row in pairs)
assert all(
    row["new_inference_type"] == "census_FM_dense_dial_2px_only"
    for row in pairs
)
assert manifest["learning_runs_started"] == 0
assert manifest["new_inference_type"] == "census_FM_dense_dial_2px_only"
assert manifest["counts"]["target_buildings"] == 58
assert manifest["counts"]["target_pairs"] == 580
pending = [row["building_id"] for row in rows if int(row["pending_pair_count"]) > 0]
unmeasurable = [
    row["building_id"]
    for row in rows
    if row["status"] in {
        "ineligible_no_summary_pair",
        "prerequisite_missing",
        "partial_with_failures",
    }
]
print(json.dumps({
    "rows": len(rows),
    "pairs": len(pairs),
    "pending_buildings": pending,
    "unmeasurable_buildings": unmeasurable,
    "new_inference_runs": manifest["new_mast3r_inference_runs"],
    "cache_reuse_runs": manifest["cache_reuse_runs"],
    "learning_runs_started": 0,
}, ensure_ascii=False))
PY
}

run_measurement() {
  write_status "C-2" "running" "58 buildings, 580 pairs, GPU budget <=6h"
  write_state "C-2" "running" "locked dense dial"
  log "C-2 measurement start budget_seconds=$FM_BUDGET_SECONDS"
  run_mast3r > "$LOG_DIR/C2_dense.log" 2>&1
  local rc="$?"
  log "C-2 dense worker exit rc=$rc"
  if [[ ! -f "$INFERENCE_CSV" || ! -f "$INFERENCE_MANIFEST" ]]; then
    issue "AC-C2 hard failure: dense worker rc=$rc; inference CSV or manifest missing; learning_runs_started=0."
    commit_stage \
      "AC-C2-PARTIAL: record dense census hard failure" \
      docs/issues.md "$RUN_REL" || true
    write_status "C-2" "failed" "worker rc=$rc and terminal outputs missing"
    write_state "C-2" "failed" "terminal outputs missing"
    return 1
  fi
  if ! measurement_qa; then
    issue "AC-C2 QA failure: dense outputs retained; log=$DRIVER_REL/logs/measurement_qa.log; learning_runs_started=0."
    commit_stage \
      "AC-C2-PARTIAL: retain dense census QA failure" \
      docs/issues.md "$RUN_REL" || true
    write_status "C-2" "failed" "measurement QA failed"
    write_state "C-2" "failed" "measurement QA failed"
    return 1
  fi
  local pending
  pending="$(
    run_dev python3 - "$INFERENCE_CSV" <<'PY'
import csv
import sys
rows=list(csv.DictReader(open(sys.argv[1], newline="", encoding="utf-8")))
print(sum(int(row["pending_pair_count"]) > 0 for row in rows))
PY
  )"
  issue "AC-C2 measurement recorded: census_rows=58; pairs=580; pending_buildings=$pending; measurements_sha256=$(sha "$INFERENCE_CSV"); pairs_sha256=$(sha "$INFERENCE_PAIRS"); progress_sha256=$(sha "$INFERENCE_PROGRESS"); inference_manifest_sha256=$(sha "$INFERENCE_MANIFEST"); learning_runs_started=0; new_inference_allowlist=$ALLOWLIST."
  if ! commit_stage \
    "AC-C2: measure fixed dense-dial anchor census" \
    docs/issues.md "$RUN_REL"; then
    write_status "C-2" "failed" "measurement commit or push failed"
    write_state "C-2" "failed" "measurement commit or push failed"
    return 1
  fi
  MEASUREMENT_COMMIT="$(git rev-parse HEAD)"
  write_status "C-2" "complete" "commit=$MEASUREMENT_COMMIT pending=$pending"
  write_state "C-2" "complete" "commit=$MEASUREMENT_COMMIT"
}

run_finalize() {
  write_status "C-3" "running" "59-row census copy and boundary_map_v4"
  write_state "C-3" "running" "aggregate and QA"
  if ! run_dev python3 "$SCRIPT" finalize \
    > "$LOG_DIR/finalize.log" 2>&1; then
    issue "AC-C3 finalize failure: log=$DRIVER_REL/logs/finalize.log; learning_runs_started=0."
    commit_stage \
      "AC-C3-PARTIAL: retain anchor census finalize failure" \
      docs/issues.md "$RUN_REL" docs/experiments/boundary_map/tables/anchor_census_measurements.csv \
      docs/archive/boundary_map/v4/tables/boundary_map_v4_ladder.csv docs/archive/boundary_map/v4/tables/boundary_map_v4_targets.csv \
      docs/experiments/boundary_map/tables/anchor_census_ambiguous_1_99.csv \
      docs/experiments/boundary_map/tables/anchor_census_high_count_high_mad.csv \
      docs/experiments/boundary_map/manifests/boundary_map_v4_manifest.json \
      docs/experiments/boundary_map/reports/W_anchor_census_boundary_map_v4_summary_20260720.md \
      docs/figs/boundary_map || true
    write_status "C-3" "failed" "finalize command failed"
    write_state "C-3" "failed" "finalize command failed"
    return 1
  fi
  if ! run_dev python3 "$SCRIPT" qa \
    > "$LOG_DIR/public_qa.log" 2>&1; then
    issue "AC-C3 public QA failure: generated outputs retained; log=$DRIVER_REL/logs/public_qa.log; learning_runs_started=0."
    commit_stage \
      "AC-C3-PARTIAL: retain boundary-map-v4 QA failure" \
      docs/issues.md "$RUN_REL" docs/experiments/boundary_map/tables/anchor_census_measurements.csv \
      docs/archive/boundary_map/v4/tables/boundary_map_v4_ladder.csv docs/archive/boundary_map/v4/tables/boundary_map_v4_targets.csv \
      docs/experiments/boundary_map/tables/anchor_census_ambiguous_1_99.csv \
      docs/experiments/boundary_map/tables/anchor_census_high_count_high_mad.csv \
      docs/experiments/boundary_map/manifests/boundary_map_v4_manifest.json \
      docs/experiments/boundary_map/reports/W_anchor_census_boundary_map_v4_summary_20260720.md \
      docs/figs/boundary_map || true
    write_status "C-3" "failed" "public QA failed"
    write_state "C-3" "failed" "public QA failed"
    return 1
  fi
  issue "AC-C3 boundary_map_v4 recorded: measurements_sha256=$(sha docs/experiments/boundary_map/tables/anchor_census_measurements.csv); run_manifest_sha256=$(sha "$RUN_MANIFEST"); ladder_sha256=$(sha docs/archive/boundary_map/v4/tables/boundary_map_v4_ladder.csv); targets_sha256=$(sha docs/archive/boundary_map/v4/tables/boundary_map_v4_targets.csv); lowcount_sha256=$(sha docs/experiments/boundary_map/tables/anchor_census_ambiguous_1_99.csv); highmad_sha256=$(sha docs/experiments/boundary_map/tables/anchor_census_high_count_high_mad.csv); public_manifest_sha256=$(sha docs/experiments/boundary_map/manifests/boundary_map_v4_manifest.json); figure_sha256=$(sha docs/figs/boundary_map/boundary_map_v4_map.png); summary_sha256=$(sha docs/experiments/boundary_map/reports/W_anchor_census_boundary_map_v4_summary_20260720.md); learning_runs_started=0."
  if ! commit_stage \
    "AC-C3: aggregate neutral boundary-map-v4 cells" \
    docs/issues.md "$RUN_REL" docs/experiments/boundary_map/tables/anchor_census_measurements.csv \
    docs/archive/boundary_map/v4/tables/boundary_map_v4_ladder.csv docs/archive/boundary_map/v4/tables/boundary_map_v4_targets.csv \
    docs/experiments/boundary_map/tables/anchor_census_ambiguous_1_99.csv \
    docs/experiments/boundary_map/tables/anchor_census_high_count_high_mad.csv \
    docs/experiments/boundary_map/manifests/boundary_map_v4_manifest.json \
    docs/experiments/boundary_map/reports/W_anchor_census_boundary_map_v4_summary_20260720.md \
    docs/figs/boundary_map; then
    write_status "C-3" "failed" "public commit or push failed"
    write_state "C-3" "failed" "public commit or push failed"
    return 1
  fi
  PUBLIC_COMMIT="$(git rev-parse HEAD)"
  write_status "C-3" "complete" "commit=$PUBLIC_COMMIT"
  write_state "C-3" "complete" "commit=$PUBLIC_COMMIT"
}

finish_ledger() {
  issue "AC-20260720 commit ledger: prep_commit=$(git log --format=%H --grep='AC-PREP:' -1); measurement_commit=$MEASUREMENT_COMMIT; public_commit=$PUBLIC_COMMIT; learning_runs_started=0; allowed_new_inference=$ALLOWLIST."
  if ! commit_stage \
    "AC-LEDGER: record anchor census commits" docs/issues.md; then
    write_status "ledger" "failed" "ledger commit or push failed"
    write_state "ledger" "failed" "ledger commit or push failed"
    return 1
  fi
  write_status "complete" "complete" \
    "measurement=$MEASUREMENT_COMMIT public=$PUBLIC_COMMIT ledger=$(git rev-parse HEAD)"
  write_state "complete" "complete" "all outputs committed and pushed"
  log "anchor census complete head=$(git rev-parse HEAD)"
}

main() {
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    log "another anchor census driver holds the lock"
    return 73
  fi
  LOCK_ACQUIRED=1
  printf "%s\n" "$$" > "$PID_FILE"
  write_status "start" "running" "detached driver entered"
  write_state "start" "running" "detached driver entered"
  preflight || return 1
  run_measurement || return 1
  run_finalize || return 1
  finish_ledger || return 1
}

main "$@"
