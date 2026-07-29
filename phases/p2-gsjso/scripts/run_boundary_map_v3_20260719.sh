#!/usr/bin/env bash
# Detached learning-zero boundary-map-v3 driver.
# Launch from the repository root:
#   mkdir -p phases/p2-gsjso/runs/20260719_boundary_map_v3_driver
#   setsid nohup bash phases/p2-gsjso/scripts/run_boundary_map_v3_20260719.sh \
#     > phases/p2-gsjso/runs/20260719_boundary_map_v3_driver/detached.log \
#     2>&1 < /dev/null &
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO" || exit 1

RUN_REL="phases/p2-gsjso/runs/20260719_boundary_map_v3_driver"
RUN="$REPO/$RUN_REL"
MEASURE_REL="phases/p2-gsjso/runs/20260719_boundary_map_v3"
MEASURE="$REPO/$MEASURE_REL"
LOG_DIR="$RUN/logs"
STATUS="$RUN/status.json"
STATE="$RUN/driver_state.json"
LOCK_FILE="$RUN/driver.lock"
PID_FILE="$RUN/launcher.pid"
CID_FILE="$RUN/fm_container.cid"
ISSUES="$REPO/docs/issues.md"
BRANCH="exp/3b-surface-restore-corrected"

DEV_IMAGE="jointbuildgs:dev"
DEV_IMAGE_ID="sha256:926b2fd5e31d9f22d44db347b703ed1acfe0a98d19c189c80324daec63fd6396"
MAST3R_IMAGE="jointbuildgs-s3ap-mast3r:20260714-f5209af"
MAST3R_IMAGE_ID="sha256:89d64b4c7112cc55db0d42d562e2a0208858658c0c67ab1bd48424175c50f501"
FM_CONTAINER_NAME="jointbuildgs-boundary-map-v3-20260719"
MODEL_REVISION="06e7259f34c3060f322df5cb0c7b9094f57e41fc"
MODEL_SHA256="0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
MODEL_BYTES=2754661648
MODEL_CONFIG_SHA256="718eb93dc4f9e4332b60cc0041af962d712cbd346d7770ce35c5b22cff68eae4"
MODEL_REPO_HOST="/home/innopam/.cache/huggingface/hub/models--naver--MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric"
MODEL_HOST="$MODEL_REPO_HOST/snapshots/$MODEL_REVISION"
MODEL_REPO_CONTAINER="/models/mast3r_metric"
MODEL_CONTAINER="$MODEL_REPO_CONTAINER/snapshots/$MODEL_REVISION"
ENV_MANIFEST="docs/e5_c001_s3ap_fm_env_manifest.json"
ENV_MANIFEST_SHA256="7246a77569a7af1b931ad60eda7012e6e3e8f4ff81b5e10f2e3c1a2efea80d68"
DENSE_DIAL_CONFIG="phases/p2-gsjso/configs/e5_c001_s3ap_fm_dense_dial.json"
DENSE_DIAL_CONFIG_SHA256="72d0bef6578b9e5cbe96fb32cbf81802d3a87a92a8da5a6b5b497baba18491c9"
DENSE_DIAL_CSV="docs/e5_c001_s3ap_fm_dense_dial.csv"
DENSE_DIAL_CSV_SHA256="5a743961cd58dc099dce3200a2465d0838dc9b4dce4f59fb787769064d4a9a26"
PIP_FREEZE="phases/p2-gsjso/runs/20260714_e5_c001_s3ap_fm_env/pip_freeze.txt"
PIP_FREEZE_SHA256="1c556c3be3304703a2971d82b4fd320fc96d2dd682787388123130db0a586b77"
MAST3R_DOCKERFILE="phases/p2-gsjso/docker/s3ap-mast3r/Dockerfile"
MAST3R_DOCKERFILE_SHA256="2ada6809de7e5d8e66a9c62875edaf47fe9ee584c4a1aec228732b7e3e0fc3fc"
V3_SCRIPT="phases/p2-gsjso/scripts/boundary_map_v3.py"
V3_DENSE_SCRIPT="phases/p2-gsjso/scripts/boundary_map_v3_dense.py"
DRIVER_SCRIPT="phases/p2-gsjso/scripts/run_boundary_map_v3_20260719.sh"
UID_GID="$(id -u):$(id -g)"
START_EPOCH="$(date +%s)"
FM_BUDGET_SECONDS=21600
FM_FINALIZE_GRACE_SECONDS=120

R1P12_COMMIT=""
R1P3_COMMIT=""
R1P4_COMMIT=""
LAST_COMMIT=""
LOCK_ACQUIRED=0

mkdir -p "$LOG_DIR" "$MEASURE"

timestamp() {
  date -u "+%Y-%m-%dT%H:%M:%SZ"
}

log() {
  printf "%s %s\n" "$(timestamp)" "$*" | tee -a "$RUN/driver.log"
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
    "task": "R1prime boundary_map_v3",
    "stage": stage,
    "state": state,
    "detail": detail,
    "elapsed_seconds": time.time() - started,
    "learning_runs_started": 0,
    "allowed_new_inference": "R1prime-3 FM dense dial only",
}, ensure_ascii=False, indent=2))
PY
  mv "$temporary" "$STATUS"
}

state_init() {
  local head
  head="$(git rev-parse HEAD)"
  python3 - "$STATE" "$BRANCH" "$head" "$FM_BUDGET_SECONDS" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
branch = sys.argv[2]
head = sys.argv[3]
limit = int(sys.argv[4])
if path.is_file():
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "jointbuildgs.boundary_map_v3.driver_state.v1":
        raise SystemExit("driver state schema mismatch")
    if payload.get("branch") != branch:
        raise SystemExit("driver state branch mismatch")
else:
    payload = {
        "schema": "jointbuildgs.boundary_map_v3.driver_state.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "branch": branch,
        "base_head": head,
        "job_sha256": "",
        "stages": {},
        "fm_budget": {
            "limit_seconds": limit,
            "started_epoch": None,
            "deadline_epoch": None,
        },
        "learning_runs_started": 0,
        "allowed_new_inference": "R1prime-3_FM_dense_dial_2px",
    }
payload["updated_utc"] = datetime.now(timezone.utc).isoformat()
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
os.replace(temporary, path)
PY
}

state_get() {
  local key="$1"
  python3 - "$STATE" "$key" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(0)
value = json.loads(path.read_text(encoding="utf-8"))
for part in sys.argv[2].split("."):
    if not isinstance(value, dict) or part not in value:
        raise SystemExit(0)
    value = value[part]
if value is None:
    raise SystemExit(0)
if isinstance(value, bool):
    print("true" if value else "false")
elif isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
else:
    print(value)
PY
}

state_set_stage() {
  local stage="$1"
  local status="$2"
  local commit="${3:-}"
  local detail="${4:-}"
  local target_status="${5:-}"
  python3 - "$STATE" "$stage" "$status" "$commit" "$detail" "$target_status" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
stage, status, commit, detail, target = sys.argv[2:7]
record = payload.setdefault("stages", {}).setdefault(stage, {})
record.update({
    "status": status,
    "commit": commit,
    "detail": detail,
    "target_status": target,
    "updated_utc": datetime.now(timezone.utc).isoformat(),
})
payload["updated_utc"] = record["updated_utc"]
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
os.replace(temporary, path)
PY
}

state_set_job_sha() {
  local digest="$1"
  python3 - "$STATE" "$digest" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["job_sha256"] = sys.argv[2]
payload["updated_utc"] = datetime.now(timezone.utc).isoformat()
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
os.replace(temporary, path)
PY
}

state_start_or_get_budget() {
  python3 - "$STATE" "$FM_BUDGET_SECONDS" <<'PY'
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
limit = int(sys.argv[2])
payload = json.loads(path.read_text(encoding="utf-8"))
budget = payload.setdefault("fm_budget", {})
now = int(time.time())
if budget.get("started_epoch") is None:
    budget["limit_seconds"] = limit
    budget["started_epoch"] = now
    budget["deadline_epoch"] = now + limit
budget["last_checked_epoch"] = now
budget["remaining_seconds"] = max(0, int(budget["deadline_epoch"]) - now)
payload["updated_utc"] = datetime.now(timezone.utc).isoformat()
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
os.replace(temporary, path)
print(budget["remaining_seconds"])
PY
}

verify_state_history() {
  local base
  local stage
  local commit
  base="$(state_get base_head)"
  if [[ -z "$base" ]] || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
    log "driver state base commit missing: $base"
    return 1
  fi
  if ! git merge-base --is-ancestor "$base" HEAD; then
    log "driver state base is not an ancestor of HEAD: base=$base"
    return 1
  fi
  for stage in R1P12 R1P3 R1P4 LEDGER; do
    commit="$(state_get "stages.$stage.commit")"
    if [[ -n "$commit" ]]; then
      if ! git cat-file -e "$commit^{commit}" 2>/dev/null \
        || ! git merge-base --is-ancestor "$commit" HEAD; then
        log "driver state stage commit is not in HEAD history: stage=$stage commit=$commit"
        return 1
      fi
    fi
  done
}

recover_committed_stages() {
  local stage
  local status
  local commit
  local target
  local detail
  local remote
  local subject
  remote="$(git rev-parse "origin/$BRANCH")"
  for stage in R1P12 R1P3 R1P4 LEDGER; do
    status="$(state_get "stages.$stage.status")"
    commit="$(state_get "stages.$stage.commit")"
    target="$(state_get "stages.$stage.target_status")"
    detail="$(state_get "stages.$stage.detail")"
    if [[ "$status" == "commit_pending" && -z "$commit" ]]; then
      subject="$(git log -1 --format=%s)"
      if [[ -n "$detail" && "$subject" == "$detail" ]]; then
        commit="$(git rev-parse HEAD)"
        state_set_stage "$stage" "push_pending" "$commit" \
          "$detail" "$target"
        status="push_pending"
      else
        log "unresolved commit_pending stage requires inspection: stage=$stage"
        return 1
      fi
    fi
    if [[ "$status" == "push_pending" ]]; then
      if [[ -z "$commit" || -z "$target" ]] \
        || ! git cat-file -e "$commit^{commit}" 2>/dev/null \
        || ! git merge-base --is-ancestor "$commit" "$remote"; then
        log "push_pending stage is not present on origin: stage=$stage commit=$commit"
        return 1
      fi
      state_set_stage "$stage" "$target" "$commit" \
        "$detail" "$target"
      log "recovered committed stage=$stage status=$target commit=$commit"
    fi
  done
}

acquire_driver_lock() {
  if ! command -v flock >/dev/null 2>&1; then
    log "flock command missing"
    return 1
  fi
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    log "another boundary-map-v3 driver holds $LOCK_FILE"
    return 1
  fi
  LOCK_ACQUIRED=1
  printf "%s\n" "$$" > "$PID_FILE"
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
    -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e XDG_CACHE_HOME=/tmp \
    -v "$REPO:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    "$DEV_IMAGE" "$@"
}

run_mast3r() {
  local outer_seconds="$1"
  local inner_seconds=$(( outer_seconds - FM_FINALIZE_GRACE_SECONDS ))
  if (( inner_seconds <= 0 )); then
    return 75
  fi
  cleanup_fm_container
  timeout --signal=TERM --kill-after=60s "${outer_seconds}s" \
    docker run --rm \
      --name "$FM_CONTAINER_NAME" \
      --cidfile "$CID_FILE" \
      --stop-timeout 30 \
      --user "$UID_GID" \
      --gpus device=0 \
      -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e XDG_CACHE_HOME=/tmp \
      -e MAST3R_DOCKER_IMAGE_ID="$MAST3R_IMAGE_ID" \
      -v "$REPO:/workspace/JointBuildGS" \
      -v "$MODEL_REPO_HOST:$MODEL_REPO_CONTAINER:ro" \
      -w /workspace/JointBuildGS \
      "$MAST3R_IMAGE" \
      python3 "$V3_DENSE_SCRIPT" \
        --model-dir "$MODEL_CONTAINER" \
        --device cuda:0 \
        --max-seconds "$inner_seconds"
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
  log "push attempts exhausted: branch=$BRANCH head=$(git rev-parse HEAD)"
  return 1
}

commit_stage() {
  local stage="$1"
  local final_status="$2"
  local message="$3"
  shift 3
  local path
  local normalized
  local staged
  local allowed
  local -a paths=()
  LAST_COMMIT=""
  if ! git diff --cached --quiet; then
    log "refusing commit with pre-existing staged changes: stage=$stage"
    return 1
  fi
  for path in "$@"; do
    normalized="$(realpath -m --relative-to="$REPO" "$path")"
    if [[ -z "$normalized" || "$normalized" == ".." \
      || "$normalized" == ../* || "$normalized" == /* ]]; then
      log "commit path is outside repository: stage=$stage path=$path"
      return 1
    fi
    paths+=("$normalized")
  done
  state_set_stage "$stage" "commit_pending" "" "$message" "$final_status"
  for path in "${paths[@]}"; do
    if [[ -e "$path" ]] \
      || git ls-files --error-unmatch -- "$path" >/dev/null 2>&1; then
      if ! git add -A -- "$path"; then
        log "git add failed: stage=$stage path=$path"
        state_set_stage "$stage" "hard_error" "" \
          "git add failed: $path" "hard_error"
        return 1
      fi
    fi
  done
  if git diff --cached --quiet; then
    log "no staged changes for unrecorded stage=$stage message=$message"
    state_set_stage "$stage" "hard_error" "" \
      "no staged changes for an unrecorded stage" "hard_error"
    return 1
  fi
  while IFS= read -r staged; do
    allowed=false
    for path in "${paths[@]}"; do
      if [[ "$staged" == "$path" || "$staged" == "$path/"* ]]; then
        allowed=true
        break
      fi
    done
    if [[ "$allowed" != true ]]; then
      log "staged path outside exact allowlist: stage=$stage path=$staged"
      state_set_stage "$stage" "hard_error" "" \
        "staged path outside allowlist: $staged" "hard_error"
      return 1
    fi
  done < <(git diff --cached --name-only)
  if ! git diff --cached --check; then
    log "staged diff check failed: stage=$stage"
    state_set_stage "$stage" "hard_error" "" \
      "git diff --cached --check failed" "hard_error"
    return 1
  fi
  if ! git commit -m "$message"; then
    log "$message commit command exited nonzero"
    state_set_stage "$stage" "hard_error" "" \
      "git commit exited nonzero" "hard_error"
    return 1
  fi
  LAST_COMMIT="$(git rev-parse HEAD)"
  state_set_stage "$stage" "push_pending" "$LAST_COMMIT" \
    "$message" "$final_status"
  if ! push_retry; then
    return 1
  fi
  state_set_stage "$stage" "$final_status" "$LAST_COMMIT" \
    "$message" "$final_status"
}

write_driver_partial_manifest() {
  local stage="$1"
  local status="$2"
  local reason="$3"
  shift 3
  local output="$MEASURE/driver_partial_${stage}.json"
  python3 - "$output" "$stage" "$status" "$reason" "$STATE" "$@" <<'PY'
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

output = Path(sys.argv[1])
stage, status, reason = sys.argv[2:5]
state_path = Path(sys.argv[5])
paths = [Path(item) for item in sys.argv[6:]]
hashes = {}
for path in paths:
    if path.is_file():
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
progress_path = Path(
    "phases/p2-gsjso/runs/20260719_boundary_map_v3/"
    "fm_dense_progress.json"
)
progress = (
    json.loads(progress_path.read_text(encoding="utf-8"))
    if progress_path.is_file() else {}
)
measurements_path = Path(
    "phases/p2-gsjso/runs/20260719_boundary_map_v3/"
    "fm_dense_measurements.csv"
)
measurements = []
if measurements_path.is_file():
    with measurements_path.open(newline="", encoding="utf-8") as handle:
        measurements = list(csv.DictReader(handle))
payload = {
    "schema": "jointbuildgs.boundary_map_v3.driver_partial.v1",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "stage": stage,
    "status": status,
    "reason": reason,
    "driver_state": (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.is_file() else {}
    ),
    "recorded_building_count": len(measurements),
    "incomplete_buildings": progress.get("incomplete_buildings", []),
    "artifact_sha256": dict(sorted(hashes.items())),
    "learning_runs_started": 0,
    "allowed_new_inference": "R1prime-3_FM_dense_dial_2px",
    "interpretation_or_verdict": None,
}
output.parent.mkdir(parents=True, exist_ok=True)
temporary = output.with_suffix(output.suffix + ".tmp")
temporary.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
os.replace(temporary, output)
PY
}

commit_partial() {
  local stage="$1"
  local terminal_status="$2"
  local reason="$3"
  shift 3
  local path
  local hashes=""
  local partial="$MEASURE_REL/driver_partial_${stage}.json"
  write_driver_partial_manifest "$stage" "$terminal_status" "$reason" "$@"
  for path in "$@"; do
    if [[ -f "$path" ]]; then
      hashes+=" $(basename "$path")_sha256=$(sha "$path");"
    fi
  done
  issue "$stage partial measurement: status=$terminal_status; reason=$reason;${hashes} partial_manifest_sha256=$(sha "$partial"); learning_runs_started=0"
  commit_stage "$stage" "$terminal_status" \
    "$stage-PARTIAL: preserve boundary-map-v3 measurements" \
    docs/issues.md \
    "$partial" \
    "$@"
}

fm_result_mode() {
  python3 - "$MEASURE/fm_dense_manifest.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    print("missing")
    raise SystemExit(0)
payload = json.loads(path.read_text(encoding="utf-8"))
status = str(payload.get("status", "missing"))
counts = payload.get("counts", {})
failed = int(counts.get("failed_pairs", 0) or 0)
prerequisite = int(counts.get("prerequisite_missing_pairs", 0) or 0)
hard_failed = max(0, failed - prerequisite)
pending = int(counts.get("pending_pairs", 0) or 0)
prerequisite_ids = payload.get("prerequisite_missing_building_ids", [])
if status == "complete" and hard_failed == 0 and pending == 0:
    print("complete")
elif status in {"budget_exhausted", "time_budget_reached"} and hard_failed == 0:
    print("budget_exhausted")
elif status == "partial" and hard_failed == 0 and pending > 0:
    print("budget_exhausted")
elif status == "partial" and hard_failed == 0 and prerequisite_ids:
    print("prerequisite_partial")
elif status == "partial" and hard_failed == 0:
    print("measurement_partial")
else:
    print("hard_error")
PY
}

normalize_budget_exhausted() {
  local reason="$1"
  local deadline
  deadline="$(state_get fm_budget.deadline_epoch)"
  run_dev python3 - "$reason" "$deadline" <<'PY'
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

reason, deadline = sys.argv[1:3]
run = Path("phases/p2-gsjso/runs/20260719_boundary_map_v3")
jobs_path = run / "fm_dense_jobs.json"
building_path = run / "fm_dense_measurements.csv"
pair_path = run / "fm_dense_pairs.csv"
progress_path = run / "fm_dense_progress.json"
manifest_path = run / "fm_dense_manifest.json"
env_path = Path("docs/e5_c001_s3ap_fm_env_manifest.json")
config_path = Path(
    "phases/p2-gsjso/configs/e5_c001_s3ap_fm_dense_dial.json"
)
dense_script = Path(
    "phases/p2-gsjso/scripts/boundary_map_v3_dense.py"
)
jobs_payload = json.loads(jobs_path.read_text(encoding="utf-8"))
jobs = jobs_payload["jobs"]
rows = []
if building_path.is_file():
    with building_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
pairs = []
if pair_path.is_file():
    with pair_path.open(newline="", encoding="utf-8") as handle:
        pairs = list(csv.DictReader(handle))
progress = (
    json.loads(progress_path.read_text(encoding="utf-8"))
    if progress_path.is_file() else {}
)
fingerprint = str(progress.get("input_fingerprint", ""))
if not fingerprint:
    raise SystemExit(
        "cannot normalize outer timeout without progress input_fingerprint"
    )
if not rows or not pairs:
    raise SystemExit(
        "cannot normalize outer timeout without linked building and pair rows"
    )
if any(row.get("input_fingerprint") != fingerprint for row in rows):
    raise SystemExit("building/progress input_fingerprint drift")
if any(row.get("input_fingerprint") != fingerprint for row in pairs):
    raise SystemExit("pair/progress input_fingerprint drift")
by_id = {row["building_id"]: row for row in rows}
incomplete = []
for job in jobs:
    row = by_id.get(job["building_id"])
    complete = (
        row is not None
        and str(row.get("measurement_complete", "")).lower()
        in {"1", "true"}
    )
    if not complete:
        incomplete.append({
            "building_id": job["building_id"],
            "status": (
                row.get("status", "not_started")
                if row is not None else "not_started"
            ),
            "failed_pair_count": int(
                (row or {}).get("failed_pair_count") or 0
            ),
            "pending_pair_count": int(
                (row or {}).get("pending_pair_count")
                or len(job.get("pairs", []))
            ),
            "elapsed_seconds": float(
                (row or {}).get("elapsed_seconds") or 0.0
            ),
        })
incomplete_ids = sorted(item["building_id"] for item in incomplete)
incomplete_id_set = set(incomplete_ids)
completed_ids = sorted(
    job["building_id"]
    for job in jobs
    if job["building_id"] not in incomplete_id_set
)
prerequisite_missing_ids = sorted(
    item["building_id"]
    for item in incomplete
    if item["status"] == "prerequisite_missing"
)
observed_pair_keys = {
    (row["building_id"], int(row["pair_rank"])) for row in pairs
}
expected_pair_keys = {
    (job["building_id"], int(pair["pair_rank"]))
    for job in jobs for pair in job.get("pairs", [])
}
missing_pair_count = len(expected_pair_keys - observed_pair_keys)
progress.update({
    "schema": "jointbuildgs.boundary_map_v3.fm_dense.progress.v1",
    "run_id": "20260719_boundary_map_v3",
    "updated_utc": datetime.now(timezone.utc).isoformat(),
    "status": "budget_exhausted",
    "input_fingerprint": fingerprint,
    "driver_budget_reason": reason,
    "driver_deadline_epoch": int(deadline) if deadline else None,
    "target_building_count": len(jobs),
    "complete_building_count": len(jobs) - len(incomplete),
    "completed_building_ids": completed_ids,
    "incomplete_building_count": len(incomplete),
    "incomplete_building_ids": incomplete_ids,
    "prerequisite_missing_building_ids": prerequisite_missing_ids,
    "target_pair_count": sum(len(job.get("pairs", [])) for job in jobs),
    "complete_or_excluded_pair_count": sum(
        row.get("status") in {"complete", "excluded_pair"} for row in pairs
    ),
    "failed_pair_count": sum(
        row.get("status") in {"failed", "prerequisite_missing"}
        for row in pairs
    ),
    "prerequisite_missing_pair_count": sum(
        row.get("status") == "prerequisite_missing" for row in pairs
    ),
    "pending_pair_count": (
        sum(row.get("status") == "pending" for row in pairs)
        + missing_pair_count
    ),
    "incomplete_buildings": incomplete,
    "learning_runs_started": 0,
    "new_inference_type": "R1prime-3_FM_dense_dial_2px",
})
temporary = progress_path.with_suffix(".json.tmp")
temporary.write_text(
    json.dumps(progress, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
os.replace(temporary, progress_path)
manifest = (
    json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest_path.is_file() else {}
)
environment = json.loads(env_path.read_text(encoding="utf-8"))
model = jobs_payload["model"]
reproduction_check = list(manifest.get("reproduction_check", []))
row199 = by_id.get("DEBY_LOD2_4907199")
if not reproduction_check and row199 is not None:
    row199_complete = str(
        row199.get("measurement_complete", "")
    ).lower() in {"1", "true"}
    reproduction_check = [{
        "building_id": "DEBY_LOD2_4907199",
        "status": "complete" if row199_complete else "pending_budget",
        "selected_dlt_point_count": row199.get(
            "selected_dlt_point_count", ""
        ),
        "expected_selected_dlt_point_count": 538,
        "footprint_inside_point_count": row199.get(
            "footprint_inside_point_count", ""
        ),
        "expected_footprint_inside_point_count": 373,
        "inside_z_median_m": row199.get("inside_z_median_m", ""),
        "expected_inside_z_median_m": -34.347425,
        "passed": (
            str(row199.get("reproduction_check_passed", "")).lower()
            in {"1", "true"}
        ),
    }]
camera_branch_counts = {
    branch: sum(row.get("camera_branch") == branch for row in pairs)
    for branch in ("c001_pinhole_binary", "p0_full_opencv_text")
}
building_camera_branch_inventory = {
    row["building_id"]: row.get("camera_branch_inventory", "")
    for row in rows
}
manifest.update({
    "schema": "jointbuildgs.boundary_map_v3.fm_dense.manifest.v1",
    "run_id": "20260719_boundary_map_v3",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "status": "budget_exhausted",
    "input_fingerprint": fingerprint,
    "jobs": str(jobs_path),
    "budget": {
        **manifest.get("budget", {}),
        "locked_upper_bound_seconds": 21600,
        "driver_deadline_epoch": int(deadline) if deadline else None,
        "driver_budget_reason": reason,
    },
    "runtime_lock": {
        **manifest.get("runtime_lock", {}),
        "docker_image_tag": model["docker_image_tag"],
        "docker_image_id": model["docker_image_id"],
        "model_id": model["model_id"],
        "model_revision": model["model_revision"],
        "weights_sha256": model["weights_sha256"],
        "weights_bytes": model["weights_bytes"],
        "config_sha256": model["model_config_sha256"],
        "environment_manifest": str(env_path),
        "environment_manifest_sha256": model[
            "environment_manifest_sha256"
        ],
        "mast3r_commit": model["mast3r_commit"],
        "dust3r_commit": model["dust3r_commit"],
        "croco_commit": model["croco_commit"],
        "python": environment["runtime_lock"]["python"],
        "torch": environment["runtime_lock"]["torch"],
        "torch_cuda": environment["runtime_lock"]["torch_cuda"],
    },
    "camera_branches": {
        "c001_pinhole_binary": {
            "camera_model": "PINHOLE",
            "frame_source": (
                "results/tum_transfer/e5_pilot/C001/"
                "data_geoidfix_C001_buf20/images"
            ),
            "camera_source": (
                "results/tum_transfer/e5_pilot/C001/"
                "data_geoidfix_C001_buf20/sparse/0/cameras.bin"
            ),
            "pose_source": (
                "results/tum_transfer/e5_pilot/C001/"
                "data_geoidfix_C001_buf20/sparse/0/images.bin"
            ),
            "scene_reference_source": None,
            "world_frame": "canonical_local_xyz",
            "crop_source": "s3ap_locked_or_frozen_region",
            "addressed_pair_count": camera_branch_counts[
                "c001_pinhole_binary"
            ],
        },
        "p0_full_opencv_text": {
            "camera_model": "FULL_OPENCV",
            "frame_source": "phases/p0-audit/data/work/images/Images",
            "camera_source": (
                "phases/p0-audit/data/work/colmap/sparse/0/cameras.txt"
            ),
            "pose_source": (
                "phases/p0-audit/data/work/colmap/sparse/0/images.txt"
            ),
            "scene_reference_source": (
                "phases/p0-audit/data/work/opf/opf/"
                "scene_reference_frame.json"
            ),
            "projection_datum_config": "configs/projection_datum.json",
            "world_frame": "canonical_local_xyz",
            "crop_source": "projected_footprint",
            "addressed_pair_count": camera_branch_counts[
                "p0_full_opencv_text"
            ],
            "same_stem_c001_fallback_allowed": False,
        },
    },
    "camera_branch_counts": camera_branch_counts,
    "building_camera_branch_inventory": (
        building_camera_branch_inventory
    ),
    "reproduction_check": reproduction_check,
    "counts": {
        "target_buildings": len(jobs),
        "complete_buildings": len(jobs) - len(incomplete),
        "incomplete_buildings": len(incomplete),
        "target_pairs": sum(len(job.get("pairs", [])) for job in jobs),
        "complete_or_excluded_pairs": progress[
            "complete_or_excluded_pair_count"
        ],
        "failed_pairs": progress["failed_pair_count"],
        "prerequisite_missing_pairs": progress[
            "prerequisite_missing_pair_count"
        ],
        "pending_pairs": progress["pending_pair_count"],
    },
    "completed_building_ids": completed_ids,
    "incomplete_building_ids": incomplete_ids,
    "prerequisite_missing_building_ids": prerequisite_missing_ids,
    "incomplete_buildings": incomplete,
    "learning_runs_started": 0,
    "new_inference_type": "R1prime-3_FM_dense_dial_2px",
    "interpretation_or_verdict": None,
    "no_seed_or_training_use": True,
})
core_sources = [
    jobs_path,
    env_path,
    config_path,
    dense_script,
]
source_hashes = dict(manifest.get("source_sha256", {}))
for path in core_sources:
    if path.is_file():
        source_hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
manifest["source_sha256"] = dict(sorted(source_hashes.items()))
output_paths = [
    building_path,
    pair_path,
    progress_path,
    run / "fm_dense.log",
]
manifest["output_sha256"] = {
    str(path): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in output_paths if path.is_file()
}
temporary = manifest_path.with_suffix(".json.tmp")
temporary.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
os.replace(temporary, manifest_path)
PY
}

preflight() {
  write_status "preflight" "running" "branch, origin, process, image, model, and GPU checks"
  local active_branch
  local required
  local head
  local remote
  local model_size
  active_branch="$(git branch --show-current)"
  if [[ "$active_branch" != "$BRANCH" ]]; then
    log "R1P preflight stopped: branch=$active_branch expected=$BRANCH"
    return 1
  fi
  if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    log "R1P preflight stopped: tracked worktree changes present"
    return 1
  fi
  if ! git fetch origin "$BRANCH" > "$LOG_DIR/git_fetch.log" 2>&1; then
    log "R1P preflight stopped: git fetch exited nonzero; log=$RUN_REL/logs/git_fetch.log"
    return 1
  fi
  head="$(git rev-parse HEAD)"
  remote="$(git rev-parse "origin/$BRANCH")"
  if [[ "$head" != "$remote" ]]; then
    if git merge-base --is-ancestor "$remote" "$head"; then
      log "preflight found local commits ahead of origin; pushing before measurement"
      if ! push_retry; then
        return 1
      fi
      remote="$(git rev-parse "origin/$BRANCH")"
    else
      log "R1P preflight stopped: local/origin branch is behind or diverged"
      return 1
    fi
  fi
  if [[ "$(git rev-parse HEAD)" != "$remote" ]]; then
    log "R1P preflight stopped: local HEAD still differs from origin/$BRANCH"
    return 1
  fi
  for required in "$DRIVER_SCRIPT" "$V3_SCRIPT" "$V3_DENSE_SCRIPT"; do
    if [[ ! -f "$required" ]]; then
      log "R1P preflight stopped: required script missing: $required"
      return 1
    fi
    if ! git ls-files --error-unmatch -- "$required" >/dev/null 2>&1; then
      log "R1P preflight stopped: required script is not tracked: $required"
      return 1
    fi
  done
  if pgrep -af "train.py|src.stage2.train|e5_c001.*train|runner.*train" \
    > "$LOG_DIR/learning_process_guard.log"; then
    log "R1P preflight stopped: learning-like process listed in $RUN_REL/logs/learning_process_guard.log"
    return 1
  fi
  if ! docker image inspect "$DEV_IMAGE" > /dev/null 2>&1; then
    log "R1P preflight stopped: Docker image missing: $DEV_IMAGE"
    return 1
  fi
  if ! docker image inspect "$MAST3R_IMAGE" > /dev/null 2>&1; then
    log "R1P preflight stopped: Docker image missing: $MAST3R_IMAGE"
    return 1
  fi
  if [[ "$(docker image inspect --format '{{.Id}}' "$DEV_IMAGE")" != "$DEV_IMAGE_ID" ]]; then
    log "R1P preflight stopped: dev Docker image ID mismatch"
    return 1
  fi
  if [[ "$(docker image inspect --format '{{.Id}}' "$MAST3R_IMAGE")" != "$MAST3R_IMAGE_ID" ]]; then
    log "R1P preflight stopped: MASt3R Docker image ID mismatch"
    return 1
  fi
  if [[ ! -f "$MODEL_HOST/model.safetensors" ]]; then
    log "R1P preflight stopped: MASt3R weight file missing"
    return 1
  fi
  if [[ "$(sha "$MODEL_HOST/model.safetensors")" != "$MODEL_SHA256" ]]; then
    log "R1P preflight stopped: MASt3R weight SHA256 mismatch"
    return 1
  fi
  model_size="$(stat -Lc '%s' "$MODEL_HOST/model.safetensors")"
  if [[ "$model_size" != "$MODEL_BYTES" ]]; then
    log "R1P preflight stopped: MASt3R weight byte count mismatch"
    return 1
  fi
  if [[ "$(sha "$MODEL_HOST/config.json")" != "$MODEL_CONFIG_SHA256" ]]; then
    log "R1P preflight stopped: MASt3R config SHA256 mismatch"
    return 1
  fi
  for required in \
    "$ENV_MANIFEST:$ENV_MANIFEST_SHA256" \
    "$DENSE_DIAL_CONFIG:$DENSE_DIAL_CONFIG_SHA256" \
    "$DENSE_DIAL_CSV:$DENSE_DIAL_CSV_SHA256" \
    "$PIP_FREEZE:$PIP_FREEZE_SHA256" \
    "$MAST3R_DOCKERFILE:$MAST3R_DOCKERFILE_SHA256"; do
    local path="${required%%:*}"
    local expected="${required#*:}"
    if [[ ! -f "$path" || "$(sha "$path")" != "$expected" ]]; then
      log "R1P preflight stopped: source lock mismatch path=$path"
      return 1
    fi
  done
  if ! run_dev python3 - "$ENV_MANIFEST" "$DENSE_DIAL_CONFIG" <<'PY' \
    > "$LOG_DIR/environment_lock_qa.log" 2>&1
import json
import sys
from pathlib import Path

environment = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
config = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
runtime = environment["runtime_lock"]
model = environment["model"]
code = environment["code"]
locked = config["runtime_lock"]
checks = {
    "environment_learning_zero": environment["learning_runs_started"] == 0,
    "image_id": runtime["docker_image_id"] == locked["docker_image_id"],
    "model_revision": model["revision"] == locked["model_revision"],
    "weights_sha256": model["weights_sha256"] == locked["weights_sha256"],
    "weights_bytes": model["weights_bytes"] == locked["weights_bytes"],
    "mast3r_commit": code["mast3r_commit"] == locked["mast3r_commit"],
    "dust3r_commit": code["dust3r_commit"] == locked["dust3r_commit"],
    "croco_commit": code["croco_commit"] == locked["croco_commit"],
    "learning_allowed": config["execution_lock"]["learning_runs_allowed"] == 0,
}
if not all(checks.values()):
    raise SystemExit(checks)
print(checks)
PY
  then
    log "R1P preflight stopped: S3Ap environment lock QA failed"
    return 1
  fi
  if ! run_dev python3 -m py_compile "$V3_SCRIPT" "$V3_DENSE_SCRIPT" \
    > "$LOG_DIR/python_compile.log" 2>&1; then
    log "R1P preflight stopped: v3 Python compile check failed"
    return 1
  fi
  if ! docker run --rm --gpus device=0 "$MAST3R_IMAGE" \
    nvidia-smi --query-gpu=name --format=csv,noheader \
    > "$LOG_DIR/gpu_preflight.log" 2>&1; then
    log "R1P preflight stopped: GPU container check exited nonzero"
    return 1
  fi
  write_status "preflight" "complete" "all start gates passed"
  log "preflight complete head=$(git rev-parse HEAD) learning_runs_started=0"
}

run_r1p12() {
  write_status "R1prime-1-2" "running" "label expansion and sign-constrained depth-2 rule"
  state_set_stage "R1P12" "running" "" "prepare-fit and QA" "complete"
  if ! run_dev python3 "$V3_SCRIPT" prepare-fit \
    > "$LOG_DIR/R1P12_prepare_fit.log" 2>&1; then
    commit_partial "R1P12" "hard_error" \
      "prepare-fit command exited nonzero; log=$RUN_REL/logs/R1P12_prepare_fit.log" \
      "$MEASURE/label_inventory.json" \
      "$MEASURE/decision_rule.json" \
      "$MEASURE/primary_predictions.csv" \
      "$MEASURE/fm_dense_jobs.json" || true
    return 1
  fi
  if ! run_dev python3 - <<'PY' > "$LOG_DIR/R1P12_qa.log" 2>&1
import csv
import json
from pathlib import Path

run = Path("phases/p2-gsjso/runs/20260719_boundary_map_v3")
inventory = json.loads((run / "label_inventory.json").read_text())
rule = json.loads((run / "decision_rule.json").read_text())
primary = list(csv.DictReader((run / "primary_predictions.csv").open()))
jobs = json.loads((run / "fm_dense_jobs.json").read_text())
metrics = {
    row["building_id"]: row
    for row in csv.DictReader(Path("docs/archive/boundary_map/v2/tables/boundary_map_v2_metrics.csv").open())
}
if inventory["canonical_count"] != 178:
    raise SystemExit("canonical population drift")
if (
    inventory["dense_success_count"] != 114
    or inventory["manual_dense_success_intersection_count"] != 0
):
    raise SystemExit("dense/manual integrity drift")
if (
    inventory["combined_calibration_count"] != 79
    or inventory["combined_validation_count"] != 79
):
    raise SystemExit("expanded split drift")
if len(primary) != 178 or len({row["building_id"] for row in primary}) != 178:
    raise SystemExit("primary row count drift")
if any(
    row.get("learning_runs_started") != "0"
    or row.get("new_inference_type")
    != "none; rule fit from frozen attributes"
    for row in primary
):
    raise SystemExit("primary learning/inference flag drift")
if (
    rule["maximum_depth"] > 2
    or rule["footprint_area_primary_predicate_count"] != 0
):
    raise SystemExit("rule depth/area contract drift")
if (
    rule["calibration_n"] != 79
    or rule["validation_n"] != 79
    or rule["learning_runs_started"] != 0
    or rule["new_inference_runs"] != 0
):
    raise SystemExit("rule calibration count drift")
if set(jobs) != {"model", "jobs"} or not jobs["jobs"]:
    raise SystemExit("FM dense queue empty")
model = jobs["model"]
if (
    model["learning_runs_started"] != 0
    or model["new_inference_type"] != "R1prime-3_FM_dense_dial_2px"
    or model["docker_image_id"]
    != "sha256:89d64b4c7112cc55db0d42d562e2a0208858658c0c67ab1bd48424175c50f501"
    or model["model_revision"]
    != "06e7259f34c3060f322df5cb0c7b9094f57e41fc"
    or model["weights_sha256"]
    != "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
):
    raise SystemExit("jobs model/environment lock drift")
primary_by_id = {row["building_id"]: row for row in primary}
manual_prefix = [
    "DEBY_LOD2_4907199",
    "DEBY_LOD2_8568391",
    "DEBY_LOD2_4908049",
    "DEBY_LOD2_4908162",
]
expected_ids = {
    row["building_id"] for row in primary
    if row["primary_assignment"] != "well_textured"
} | set(manual_prefix)
job_rows = jobs["jobs"]
job_ids = [row["building_id"] for row in job_rows]
if (
    len(job_rows) != 7
    or
    len(job_ids) != len(set(job_ids))
    or set(job_ids) != expected_ids
    or job_ids[:4] != manual_prefix
):
    raise SystemExit("FM dense queue identifier/prefix drift")
if [int(row["priority_rank"]) for row in job_rows] != list(
    range(1, len(job_rows) + 1)
):
    raise SystemExit("FM dense priority rank drift")
group_order = {
    "manual_textureless": 0,
    "canonical_C001": 1,
    "remaining_area_desc": 2,
}
groups = [group_order[row["priority_group"]] for row in job_rows]
if groups != sorted(groups):
    raise SystemExit("FM dense priority group order drift")
remaining = [
    row["building_id"] for row in job_rows
    if row["priority_group"] == "remaining_area_desc"
]
expected_remaining = sorted(
    remaining,
    key=lambda building_id: (
        -float(metrics[building_id]["footprint_area_m2"]),
        building_id,
    ),
)
if remaining != expected_remaining:
    raise SystemExit("FM dense remaining area order drift")
for job in job_rows:
    if not job.get("pairs"):
        raise SystemExit(f"FM dense job has no pairs: {job['building_id']}")
    expected_crop_source = (
        "s3ap_locked_pjpl_semantic_region"
        if job["building_id"] in {
            "DEBY_LOD2_4907199",
            "DEBY_LOD2_8568391",
        }
        else (
            "v2_projected_footprint_at_LoD2_height_"
            "projection_classification_only"
        )
    )
    if {
        pair["crop_source"] for pair in job["pairs"]
    } != {expected_crop_source}:
        raise SystemExit(
            "FM dense job crop/camera source branch drift: "
            f"{job['building_id']}"
        )
    ranks = [int(pair["pair_rank"]) for pair in job["pairs"]]
    if ranks != list(range(1, len(ranks) + 1)):
        raise SystemExit(f"FM dense pair rank drift: {job['building_id']}")
if inventory["learning_runs_started"] != 0 or inventory["new_inference_runs"] != 0:
    raise SystemExit("label inventory learning/inference drift")
print({
    "primary_rows": len(primary),
    "calibration": inventory["combined_calibration_count"],
    "validation": inventory["combined_validation_count"],
    "jobs": len(jobs["jobs"]),
})
PY
  then
    commit_partial "R1P12" "hard_error" \
      "QA command exited nonzero; log=$RUN_REL/logs/R1P12_qa.log" \
      "$MEASURE/label_inventory.json" \
      "$MEASURE/decision_rule.json" \
      "$MEASURE/primary_predictions.csv" \
      "$MEASURE/fm_dense_jobs.json" || true
    return 1
  fi
  issue "R1P-12 measurement complete: label_inventory_sha256=$(sha "$MEASURE/label_inventory.json"); rule_sha256=$(sha "$MEASURE/decision_rule.json"); primary_sha256=$(sha "$MEASURE/primary_predictions.csv"); jobs_sha256=$(sha "$MEASURE/fm_dense_jobs.json"); learning_runs_started=0; new_inference_runs=0"
  if ! commit_stage "R1P12" "complete" \
    "R1P-12: expand labels and fit sign-constrained rule" \
    docs/issues.md \
    "$MEASURE/label_inventory.json" \
    "$MEASURE/decision_rule.json" \
    "$MEASURE/primary_predictions.csv" \
    "$MEASURE/fm_dense_jobs.json"; then
    return 1
  fi
  R1P12_COMMIT="$LAST_COMMIT"
  state_set_job_sha "$(sha "$MEASURE/fm_dense_jobs.json")"
  write_status "R1prime-1-2" "complete" "commit=$R1P12_COMMIT"
}

run_r1p3() {
  local remaining
  local rc
  local mode
  local recorded_job_sha
  write_status "R1prime-3" "running" "S3Ap-locked 2px FM dense measurement"
  state_set_stage "R1P3" "running" "" "FM dense queue" "complete"
  recorded_job_sha="$(state_get job_sha256)"
  if [[ -z "$recorded_job_sha" || "$recorded_job_sha" != "$(sha "$MEASURE/fm_dense_jobs.json")" ]]; then
    commit_partial "R1P3" "hard_error" \
      "FM dense job fingerprint differs from persisted R1P12 state" \
      "$MEASURE/fm_dense_jobs.json" || true
    return 1
  fi
  if pgrep -af "train.py|src.stage2.train|e5_c001.*train|runner.*train" \
    > "$LOG_DIR/R1P3_learning_process_guard.log"; then
    commit_partial "R1P3" "hard_error" \
      "learning-like process present immediately before GPU launch" \
      "$MEASURE/fm_dense_jobs.json" || true
    return 1
  fi
  remaining="$(state_start_or_get_budget)"
  if (( remaining <= FM_FINALIZE_GRACE_SECONDS )); then
    rc=75
  else
    run_mast3r "$remaining" > "$LOG_DIR/R1P3_fm_dense.log" 2>&1
    rc="$?"
  fi
  if (( rc == 0 )); then
    mode="$(fm_result_mode)"
  elif (( rc == 75 || rc == 124 )); then
    if ! normalize_budget_exhausted "driver_timeout_or_no_remaining_seconds_rc_$rc"; then
      commit_partial "R1P3" "hard_error" \
        "budget-exhausted normalization failed after rc=$rc" \
        "$MEASURE/fm_dense_measurements.csv" \
        "$MEASURE/fm_dense_pairs.csv" \
        "$MEASURE/fm_dense_progress.json" \
        "$MEASURE/fm_dense_manifest.json" || true
      return 1
    fi
    mode="budget_exhausted"
  else
    commit_partial "R1P3" "hard_error" \
      "FM dense command hard error rc=$rc; log=$RUN_REL/logs/R1P3_fm_dense.log" \
      "$MEASURE/fm_dense_measurements.csv" \
      "$MEASURE/fm_dense_pairs.csv" \
      "$MEASURE/fm_dense_progress.json" \
      "$MEASURE/fm_dense_manifest.json" || true
    return 1
  fi
  if [[ "$mode" == "hard_error" || "$mode" == "missing" ]]; then
    commit_partial "R1P3" "hard_error" \
      "FM dense manifest/progress reported hard error mode=$mode" \
      "$MEASURE/fm_dense_measurements.csv" \
      "$MEASURE/fm_dense_pairs.csv" \
      "$MEASURE/fm_dense_progress.json" \
      "$MEASURE/fm_dense_manifest.json" || true
    return 1
  fi
  if ! run_dev python3 - "$mode" <<'PY' > "$LOG_DIR/R1P3_qa.log" 2>&1
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

mode = sys.argv[1]
run = Path("phases/p2-gsjso/runs/20260719_boundary_map_v3")
jobs = json.loads((run / "fm_dense_jobs.json").read_text())["jobs"]
rows = (
    list(csv.DictReader((run / "fm_dense_measurements.csv").open()))
    if (run / "fm_dense_measurements.csv").is_file() else []
)
pairs = (
    list(csv.DictReader((run / "fm_dense_pairs.csv").open()))
    if (run / "fm_dense_pairs.csv").is_file() else []
)
progress = json.loads((run / "fm_dense_progress.json").read_text())
manifest = json.loads((run / "fm_dense_manifest.json").read_text())
fingerprint = str(manifest.get("input_fingerprint", ""))
if (
    not fingerprint
    or progress.get("input_fingerprint") != fingerprint
    or any(row.get("input_fingerprint") != fingerprint for row in rows)
    or any(row.get("input_fingerprint") != fingerprint for row in pairs)
):
    raise SystemExit("dense manifest/progress/row/pair fingerprint drift")
job_ids = [job["building_id"] for job in jobs]
row_ids = [row["building_id"] for row in rows]
if len(row_ids) != len(set(row_ids)) or not set(row_ids) <= set(job_ids):
    raise SystemExit("dense building identifier duplicate/unexpected")
expected_pair_keys = {
    (job["building_id"], int(pair["pair_rank"]))
    for job in jobs for pair in job["pairs"]
}
pair_keys = [
    (row["building_id"], int(row["pair_rank"])) for row in pairs
]
if len(pair_keys) != len(set(pair_keys)) or not set(pair_keys) <= expected_pair_keys:
    raise SystemExit("dense pair identifier duplicate/unexpected")
required_building_fields = {
    "building_id", "status", "measurement_complete",
    "selected_dlt_point_count", "footprint_inside_point_count",
    "inside_z_median_m", "inside_z_mad_m",
    "inside_z_median_local_m", "coverage_ratio",
    "selected_pair_count", "completed_pair_count", "failed_pair_count",
    "pending_pair_count", "elapsed_seconds",
    "elapsed_seconds_this_invocation", "learning_runs_started",
    "new_inference_type", "input_fingerprint",
    "crop_source_inventory", "camera_branch_inventory",
    "frame_source_inventory", "camera_model_inventory",
    "world_frame_inventory", "triangulation_rule_inventory",
}
if rows and not required_building_fields <= set(rows[0]):
    raise SystemExit("dense building schema missing required columns")
required_pair_fields = {
    "building_id", "pair_rank", "crop_source", "camera_branch",
    "frame_source", "camera_model", "camera_source", "pose_source",
    "scene_reference_source", "world_frame", "triangulation_rule",
    "status", "learning_runs_started", "new_inference_type",
}
if pairs and not required_pair_fields <= set(pairs[0]):
    raise SystemExit("dense pair schema missing camera provenance columns")
if any(
    row.get("learning_runs_started") != "0"
    or row.get("new_inference_type") != "R1prime-3_FM_dense_dial_2px"
    for row in rows + pairs
):
    raise SystemExit("dense learning/inference type drift")
for row in rows:
    elapsed = float(row["elapsed_seconds"])
    invocation = float(row["elapsed_seconds_this_invocation"])
    if not math.isfinite(elapsed) or elapsed < 0 or not math.isfinite(invocation) or invocation < 0:
        raise SystemExit(f"dense elapsed-time drift: {row['building_id']}")
hard_failed_pairs = [
    row for row in pairs if row["status"] == "failed"
]
if hard_failed_pairs:
    raise SystemExit(f"dense hard failed pairs: {len(hard_failed_pairs)}")
branch_by_crop = {
    "s3ap_locked_or_frozen_region": (
        "c001_pinhole_binary", "PINHOLE"
    ),
    "projected_footprint": (
        "p0_full_opencv_text", "FULL_OPENCV"
    ),
}
for row in pairs:
    expected_branch = branch_by_crop.get(row["crop_source"])
    if expected_branch is None or (
        row["camera_branch"], row["camera_model"]
    ) != expected_branch:
        raise SystemExit(
            "dense crop/camera-branch provenance drift: "
            f"{row['building_id']} pair={row['pair_rank']}"
        )
    if row["world_frame"] != "canonical_local_xyz":
        raise SystemExit("dense camera world-frame drift")
    if row["camera_branch"] == "p0_full_opencv_text":
        if (
            row["frame_source"]
            != "phases/p0-audit/data/work/images/Images"
            or row["camera_source"]
            != "phases/p0-audit/data/work/colmap/sparse/0/cameras.txt"
            or row["pose_source"]
            != "phases/p0-audit/data/work/colmap/sparse/0/images.txt"
            or row["scene_reference_source"]
            != (
                "phases/p0-audit/data/work/opf/opf/"
                "scene_reference_frame.json"
            )
            or "FULL_OPENCV" not in row["triangulation_rule"]
            or "original" not in row["triangulation_rule"]
        ):
            raise SystemExit(
                "dense projected pair did not use frozen P0 FULL_OPENCV "
                f"provenance: {row['building_id']} pair={row['pair_rank']}"
            )
    elif (
        row["scene_reference_source"] != ""
        or "PINHOLE" not in row["triangulation_rule"]
    ):
        raise SystemExit(
            "dense C001 pair provenance drift: "
            f"{row['building_id']} pair={row['pair_rank']}"
        )
complete_ids = {
    row["building_id"] for row in rows
    if row["measurement_complete"].lower() in {"1", "true"}
}
incomplete_ids = set(job_ids) - complete_ids
manifest_incomplete = set(manifest.get("incomplete_building_ids", []))
progress_incomplete = set(progress.get("incomplete_building_ids", []))
if manifest_incomplete != incomplete_ids or progress_incomplete != incomplete_ids:
    raise SystemExit("dense incomplete-building inventory drift")
if (
    manifest.get("learning_runs_started") != 0
    or progress.get("learning_runs_started") != 0
    or manifest.get("new_inference_type") != "R1prime-3_FM_dense_dial_2px"
    or progress.get("new_inference_type") != "R1prime-3_FM_dense_dial_2px"
):
    raise SystemExit("dense manifest/progress learning contract drift")
if mode == "complete":
    if (
        manifest.get("status") != "complete"
        or progress.get("status") != "complete"
        or len(rows) != len(jobs)
        or incomplete_ids
        or set(pair_keys) != expected_pair_keys
    ):
        raise SystemExit("dense complete-mode cardinality/status drift")
elif mode == "budget_exhausted":
    if (
        manifest.get("status")
        not in {"budget_exhausted", "time_budget_reached"}
        or progress.get("status")
        not in {"budget_exhausted", "time_budget_reached"}
    ):
        raise SystemExit("dense budget-exhausted status drift")
    if not incomplete_ids:
        raise SystemExit("budget-exhausted mode has no incomplete buildings")
elif mode == "prerequisite_partial":
    prereq = set(manifest.get("prerequisite_missing_building_ids", []))
    if manifest.get("status") != "partial" or not prereq or not prereq <= incomplete_ids:
        raise SystemExit("dense prerequisite-partial inventory drift")
elif mode == "measurement_partial":
    if (
        manifest.get("status") != "partial"
        or progress.get("status") != "partial"
        or not incomplete_ids
    ):
        raise SystemExit("dense measurement-partial inventory/status drift")
else:
    raise SystemExit(f"unsupported runner mode: {mode}")
row199 = next(
    (row for row in rows if row["building_id"] == "DEBY_LOD2_4907199"),
    None,
)
reproduction_rows = [
    row for row in manifest.get("reproduction_check", [])
    if row.get("building_id") == "DEBY_LOD2_4907199"
]
row199_complete = (
    row199 is not None
    and row199["measurement_complete"].lower() in {"1", "true"}
)
if row199_complete:
    if (
        int(row199["selected_dlt_point_count"]) != 538
        or int(row199["footprint_inside_point_count"]) != 373
        or abs(
            float(row199["inside_z_median_local_m"]) - (-34.347425)
        ) > 1e-6
        or len(reproduction_rows) != 1
        or reproduction_rows[0].get("passed") not in {True, "true", 1}
    ):
        raise SystemExit(f"4907199 S3Ap reproduction drift: {row199}")
else:
    if (
        "DEBY_LOD2_4907199" not in incomplete_ids
        or len(reproduction_rows) != 1
        or reproduction_rows[0].get("passed") not in {
            False, "false", 0, "", None
        }
    ):
        raise SystemExit(
            "4907199 reproduction is neither complete-exact nor "
            "explicitly recorded pending"
        )
runtime = manifest["runtime_lock"]
if (
    runtime["docker_image_id"]
    != "sha256:89d64b4c7112cc55db0d42d562e2a0208858658c0c67ab1bd48424175c50f501"
    or runtime["model_revision"]
    != "06e7259f34c3060f322df5cb0c7b9094f57e41fc"
    or runtime["weights_sha256"]
    != "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
    or runtime["environment_manifest_sha256"]
    != "7246a77569a7af1b931ad60eda7012e6e3e8f4ff81b5e10f2e3c1a2efea80d68"
):
    raise SystemExit("dense runtime lock drift")
camera_branches = manifest.get("camera_branches", {})
if set(camera_branches) != {
    "c001_pinhole_binary",
    "p0_full_opencv_text",
}:
    raise SystemExit("dense camera-branch manifest inventory drift")
c001_branch = camera_branches["c001_pinhole_binary"]
p0_branch = camera_branches["p0_full_opencv_text"]
if (
    c001_branch.get("camera_model") != "PINHOLE"
    or c001_branch.get("crop_source")
    != "s3ap_locked_or_frozen_region"
    or p0_branch.get("camera_model") != "FULL_OPENCV"
    or p0_branch.get("crop_source") != "projected_footprint"
    or p0_branch.get("same_stem_c001_fallback_allowed") is not False
    or p0_branch.get("camera_source")
    != "phases/p0-audit/data/work/colmap/sparse/0/cameras.txt"
    or p0_branch.get("pose_source")
    != "phases/p0-audit/data/work/colmap/sparse/0/images.txt"
):
    raise SystemExit("dense camera-branch manifest provenance drift")
measured_branch_counts = {
    branch: sum(row["camera_branch"] == branch for row in pairs)
    for branch in camera_branches
}
if (
    manifest.get("camera_branch_counts") != measured_branch_counts
    or any(
        int(camera_branches[branch]["addressed_pair_count"])
        != measured_branch_counts[branch]
        for branch in camera_branches
    )
):
    raise SystemExit("dense camera-branch count drift")
building_branch_inventory = {
    row["building_id"]: row["camera_branch_inventory"] for row in rows
}
if (
    manifest.get("building_camera_branch_inventory")
    != building_branch_inventory
):
    raise SystemExit("dense building camera-branch inventory drift")
for label in ("source_sha256", "output_sha256"):
    for relative, expected in manifest.get(label, {}).items():
        path = Path(relative)
        locked_external = {
            (
                "/models/mast3r_metric/snapshots/"
                "06e7259f34c3060f322df5cb0c7b9094f57e41fc/"
                "model.safetensors"
            ): (
                "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
            ),
            (
                "/models/mast3r_metric/snapshots/"
                "06e7259f34c3060f322df5cb0c7b9094f57e41fc/"
                "config.json"
            ): (
                "718eb93dc4f9e4332b60cc0041af962d712cbd346d7770ce35c5b22cff68eae4"
            ),
            (
                "/models/mast3r_metric/blobs/"
                "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
            ): (
                "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
            ),
            (
                "/models/mast3r_metric/blobs/"
                "e485617403af6e7900f6157a399a379176b61656"
            ): (
                "718eb93dc4f9e4332b60cc0041af962d712cbd346d7770ce35c5b22cff68eae4"
            ),
        }
        if path.is_absolute():
            if relative not in locked_external or expected != locked_external[relative]:
                raise SystemExit(
                    f"dense unrecognized external source: {relative}"
                )
            continue
        if not path.is_file():
            raise SystemExit(f"dense {label} missing path: {relative}")
        measured = hashlib.sha256(path.read_bytes()).hexdigest()
        if measured != expected:
            raise SystemExit(f"dense {label} drift: {relative}")
required_sources = {
    "phases/p2-gsjso/scripts/boundary_map_v3_dense.py",
    "phases/p2-gsjso/runs/20260719_boundary_map_v3/fm_dense_jobs.json",
    "docs/e5_c001_s3ap_fm_env_manifest.json",
    "phases/p2-gsjso/configs/e5_c001_s3ap_fm_dense_dial.json",
}
if not required_sources <= set(manifest["source_sha256"]):
    raise SystemExit("dense manifest required source hashes missing")
print({
    "mode": mode,
    "buildings": len(rows),
    "complete": len(complete_ids),
    "incomplete": len(incomplete_ids),
    "pairs": len(pairs),
    "reproduction_4907199": (
        "538/373/-34.347425" if row199_complete else "pending"
    ),
})
PY
  then
    commit_partial "R1P3" "hard_error" \
      "FM dense QA command exited nonzero; log=$RUN_REL/logs/R1P3_qa.log" \
      "$MEASURE/fm_dense_measurements.csv" \
      "$MEASURE/fm_dense_pairs.csv" \
      "$MEASURE/fm_dense_progress.json" \
      "$MEASURE/fm_dense_manifest.json" || true
    return 1
  fi
  if [[ "$mode" == "complete" ]]; then
    issue "R1P-3 measurement complete: dense_sha256=$(sha "$MEASURE/fm_dense_measurements.csv"); pairs_sha256=$(sha "$MEASURE/fm_dense_pairs.csv"); progress_sha256=$(sha "$MEASURE/fm_dense_progress.json"); manifest_sha256=$(sha "$MEASURE/fm_dense_manifest.json"); learning_runs_started=0; new_inference=R1prime-3_FM_dense_dial_2px_only"
    if ! commit_stage "R1P3" "complete" \
      "R1P-3: measure FM dense dial candidates" \
      docs/issues.md \
      "$MEASURE_REL"; then
      return 1
    fi
  else
    if ! commit_partial "R1P3" "$mode" \
      "FM dense terminal measurement state=$mode; finalization remains enabled" \
      "$MEASURE/fm_dense_measurements.csv" \
      "$MEASURE/fm_dense_pairs.csv" \
      "$MEASURE/fm_dense_progress.json" \
      "$MEASURE/fm_dense_manifest.json"; then
      return 1
    fi
  fi
  R1P3_COMMIT="$LAST_COMMIT"
  write_status "R1prime-3" "$mode" "commit=$R1P3_COMMIT; finalize enabled"
}

run_r1p4() {
  write_status "R1prime-4" "running" "threshold, overrides, v3 CSVs, map, and summary"
  state_set_stage "R1P4" "running" "" "finalize and public-bundle QA" "complete"
  if ! run_dev python3 "$V3_SCRIPT" finalize \
    > "$LOG_DIR/R1P4_finalize.log" 2>&1; then
    commit_partial "R1P4" "hard_error" \
      "finalize command exited nonzero; log=$RUN_REL/logs/R1P4_finalize.log" \
      docs/experiments/boundary_map/tables/boundary_map_v3_metrics.csv \
      docs/archive/boundary_map/v3/tables/boundary_map_v3_ladder.csv \
      docs/experiments/boundary_map/tables/boundary_map_v3_confusion.csv \
      docs/experiments/boundary_map/tables/boundary_map_v3_conditional_targets.csv \
      docs/experiments/boundary_map/manifests/boundary_map_v3_manifest.json \
      docs/archive/boundary_map/v3/reports/W_boundary_map_v3_summary_20260719.md \
      docs/figs/boundary_map_v3 \
      "$MEASURE_REL" || true
    return 1
  fi
  if ! run_dev python3 - <<'PY' > "$LOG_DIR/R1P4_qa.log" 2>&1
import csv
import hashlib
import json
from pathlib import Path

docs = Path("docs")
run = Path("phases/p2-gsjso/runs/20260719_boundary_map_v3")
def rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

metrics = rows(docs / "boundary_map_v3_metrics.csv")
ladder = rows(docs / "boundary_map_v3_ladder.csv")
confusion = rows(docs / "boundary_map_v3_confusion.csv")
targets = rows(docs / "boundary_map_v3_conditional_targets.csv")
manifest = json.loads(
    (docs / "boundary_map_v3_manifest.json").read_text(encoding="utf-8")
)
metric_ids = [row["building_id"] for row in metrics]
ladder_ids = [row["building_id"] for row in ladder]
if (
    len(metric_ids) != 178
    or len(set(metric_ids)) != 178
    or len(ladder_ids) != 178
    or len(set(ladder_ids)) != 178
    or set(metric_ids) != set(ladder_ids)
):
    raise SystemExit("v3 canonical population identifier drift")
if any(
    row.get("learning_runs_started") != "0"
    for bundle in (metrics, ladder, confusion, targets)
    for row in bundle
):
    raise SystemExit("v3 learning flag drift")
allowed_row_inference = {
    "R1prime-3_FM_dense_dial_2px",
    "none; existing measurements reused read-only",
}
if any(
    row.get("new_inference_type") not in allowed_row_inference
    for bundle in (metrics, ladder, targets)
    for row in bundle
):
    raise SystemExit("v3 public-row inference provenance drift")
population = manifest.get("population", {})
if population != {
    "canonical_count": 178,
    "dense_success_count": 114,
    "dense_failure_count": 64,
    "manual_label_count": 44,
    "manual_dense_success_intersection_count": 0,
    "combined_calibration_count": 79,
    "combined_validation_count": 79,
}:
    raise SystemExit(f"v3 manifest population drift: {population}")
if (
    manifest.get("learning_runs_started") != 0
    or manifest.get("new_inference_type")
    != ["R1prime-3_FM_dense_dial_2px"]
    or manifest.get("reference_lod2_role")
    != "projection and classification only"
    or manifest.get("interpretation_or_verdict") is not None
):
    raise SystemExit("v3 manifest learning/inference/reference-role drift")
validation = manifest.get("primary_validation", {})
if (
    validation.get("n") != 79
    or validation.get("rule_status") not in {"passed_gain", "failed_gain"}
    or manifest.get("rule_status") != validation.get("rule_status")
):
    raise SystemExit("v3 primary validation/rule_status drift")
validation_rows = [
    row for row in confusion
    if row["record_type"] == "validation_accuracy"
    and row["comparison"] == "primary_rule_validation"
]
constant_rows = [
    row for row in confusion
    if row["record_type"] == "constant_gain"
    and row["comparison"] == "primary_rule_vs_constant_well_textured"
]
class_rows = [
    row for row in confusion
    if row["record_type"] == "class_metric"
    and row["comparison"] == "primary_rule_validation"
]
expected_labels = {
    "well_textured",
    "textureless_correspondence_anchored",
    "outline_only",
}
if (
    len(validation_rows) != 1
    or len(constant_rows) != 1
    or len(class_rows) != 3
    or {row["metric_label"] for row in class_rows} != expected_labels
    or int(validation_rows[0]["n_records"]) != 79
    or int(constant_rows[0]["n_records"]) != 79
):
    raise SystemExit("v3 validation/confusion required-row drift")
for comparison in (
    "primary_rule_vs_dense_success",
    "final_map_vs_dense_success",
):
    cells = [
        row for row in confusion
        if row["record_type"] == "confusion_cell"
        and row["comparison"] == comparison
    ]
    if (
        len(cells) != 4
        or sum(int(row["count"]) for row in cells) != 178
        or sum(
            int(row["count"]) for row in cells
            if row["actual_label"] == "dense_success"
        ) != 114
        or sum(
            int(row["count"]) for row in cells
            if row["actual_label"] == "dense_failure"
        ) != 64
    ):
        raise SystemExit(f"v3 dense cross-tab drift: {comparison}")
by_id = {row["building_id"]: row for row in ladder}
evidence = (
    "B-1_measured_flat_seed(FM 앵커 373·456점·"
    "W_밤샘3과제_검수_20260717 §3-1)"
)
for bid in ("DEBY_LOD2_4907199", "DEBY_LOD2_8568391"):
    row = by_id[bid]
    if (
        row["override_assignment"]
        != "textureless_correspondence_anchored"
        or row["override_evidence"] != evidence
        or row["override_applied"] != "true"
        or row["map_assignment"]
        != "textureless_correspondence_anchored"
    ):
        raise SystemExit(f"override record drift: {bid}")
overrides = manifest.get("overrides", {})
if (
    overrides.get("assignment")
    != "textureless_correspondence_anchored"
    or set(overrides.get("buildings", []))
    != {"DEBY_LOD2_4907199", "DEBY_LOD2_8568391"}
    or overrides.get("evidence") != evidence
    or any(
        overrides.get("records", {}).get(bid, {}).get("map_assignment")
        != "textureless_correspondence_anchored"
        for bid in ("DEBY_LOD2_4907199", "DEBY_LOD2_8568391")
    )
):
    raise SystemExit("v3 manifest override drift")
target_ids = {row["building_id"] for row in targets}
expected_target_ids = {
    row["building_id"] for row in ladder
    if row["map_assignment"] in {
        "textureless_correspondence_anchored",
        "outline_only",
    }
}
if (
    len(target_ids) != len(targets)
    or target_ids != expected_target_ids
    or set(manifest.get("conditional_generation_buildings", []))
    != expected_target_ids
):
    raise SystemExit("v3 conditional-target set drift")
threshold_selection = manifest.get(
    "fm_dense_count_threshold_selection", {}
)
if (
    not threshold_selection.get("status")
    or "completed_calibration_candidate_support_n"
    not in threshold_selection
    or "calibration_candidate_total_n" not in threshold_selection
    or "selected" not in threshold_selection
):
    raise SystemExit("v3 dense-threshold support record missing")
completed_support = int(
    threshold_selection["completed_calibration_candidate_support_n"]
)
total_support = int(
    threshold_selection["calibration_candidate_total_n"]
)
if (
    completed_support < 0
    or total_support < completed_support
    or bool(threshold_selection.get("available"))
    != (completed_support > 0)
):
    raise SystemExit("v3 dense-threshold support drift")
expected_sources = {
    "docs/regression_input_snapshot.csv",
    "docs/manual_review_judgments.csv",
    "docs/archive/boundary_map/v2/tables/boundary_map_v2_metrics.csv",
    "docs/archive/boundary_map/v2/tables/boundary_map_v2_ladder.csv",
    "docs/experiments/boundary_map/manifests/boundary_map_v2_manifest.json",
    "phases/p2-gsjso/runs/20260718_boundary_map_v2/all_projection_jobs.json",
    "phases/p2-gsjso/scripts/boundary_map_v2.py",
    "phases/p2-gsjso/scripts/boundary_map_v3_dense.py",
    "phases/p2-gsjso/scripts/run_boundary_map_v3_20260719.sh",
    "docs/e5_c001_s3ap_fm_env_manifest.json",
    "phases/p2-gsjso/configs/e5_c001_s3ap_fm_dense_dial.json",
    "docs/e5_c001_s3ap_fm_dense_dial.csv",
    (
        "results/tum_transfer/e5_s3_semantic_guided/C001/runs/"
        "gs_e5_C001_s3a_semantic_guided_gate/audit/"
        "pjpl_depth_anchor_views.csv"
    ),
    "phases/p2-gsjso/scripts/boundary_map_v3.py",
    str(run / "primary_predictions.csv"),
    str(run / "decision_rule.json"),
    str(run / "label_inventory.json"),
    str(run / "fm_dense_jobs.json"),
    str(run / "fm_dense_measurements.csv"),
    str(run / "fm_dense_pairs.csv"),
    str(run / "fm_dense_progress.json"),
    str(run / "fm_dense_manifest.json"),
}
expected_outputs = {
    "docs/experiments/boundary_map/tables/boundary_map_v3_metrics.csv",
    "docs/archive/boundary_map/v3/tables/boundary_map_v3_ladder.csv",
    "docs/experiments/boundary_map/tables/boundary_map_v3_confusion.csv",
    "docs/experiments/boundary_map/tables/boundary_map_v3_conditional_targets.csv",
    "docs/archive/boundary_map/v3/figs/boundary_map_v3_map.png",
    "docs/archive/boundary_map/v3/reports/W_boundary_map_v3_summary_20260719.md",
    str(run / "primary_predictions.csv"),
    str(run / "decision_rule.json"),
    str(run / "label_inventory.json"),
    str(run / "fm_dense_jobs.json"),
    str(run / "fm_dense_measurements.csv"),
    str(run / "fm_dense_pairs.csv"),
    str(run / "fm_dense_progress.json"),
    str(run / "fm_dense_manifest.json"),
}
for optional in (run / "partial_manifest.json", run / "partial_summary.md"):
    if optional.is_file():
        expected_outputs.add(str(optional))
if set(manifest.get("source_sha256", {})) != expected_sources:
    raise SystemExit("v3 manifest source inventory drift")
if set(manifest.get("output_sha256", {})) != expected_outputs:
    raise SystemExit("v3 manifest output inventory drift")
for label in ("source_sha256", "output_sha256"):
  for relative, expected in manifest[label].items():
    path = Path(relative)
    if not path.is_file():
        raise SystemExit(f"manifest {label} path missing: {relative}")
    measured = hashlib.sha256(path.read_bytes()).hexdigest()
    if measured != expected:
        raise SystemExit(f"manifest {label} SHA drift: {relative}")
for path in (
    docs / "W_boundary_map_v3_summary_20260719.md",
    docs / "figs/boundary_map_v3/boundary_map_v3_map.png",
):
    if not path.is_file():
        raise SystemExit(f"v3 output missing: {path}")
print({
    "metrics": len(metrics),
    "targets": len(targets),
    "validation_n": validation["n"],
    "rule_status": manifest["rule_status"],
    "fm_dense_status": manifest["fm_dense"]["measurement_status"],
    "threshold_support": [completed_support, total_support],
})
PY
  then
    commit_partial "R1P4" "hard_error" \
      "QA command exited nonzero; log=$RUN_REL/logs/R1P4_qa.log" \
      docs/experiments/boundary_map/tables/boundary_map_v3_metrics.csv \
      docs/archive/boundary_map/v3/tables/boundary_map_v3_ladder.csv \
      docs/experiments/boundary_map/tables/boundary_map_v3_confusion.csv \
      docs/experiments/boundary_map/tables/boundary_map_v3_conditional_targets.csv \
      docs/experiments/boundary_map/manifests/boundary_map_v3_manifest.json \
      docs/archive/boundary_map/v3/reports/W_boundary_map_v3_summary_20260719.md \
      docs/figs/boundary_map_v3 \
      "$MEASURE_REL" || true
    return 1
  fi
  issue "R1P-4 measurement complete: metrics_sha256=$(sha docs/experiments/boundary_map/tables/boundary_map_v3_metrics.csv); ladder_sha256=$(sha docs/archive/boundary_map/v3/tables/boundary_map_v3_ladder.csv); confusion_sha256=$(sha docs/experiments/boundary_map/tables/boundary_map_v3_confusion.csv); targets_sha256=$(sha docs/experiments/boundary_map/tables/boundary_map_v3_conditional_targets.csv); manifest_sha256=$(sha docs/experiments/boundary_map/manifests/boundary_map_v3_manifest.json); figure_sha256=$(sha docs/archive/boundary_map/v3/figs/boundary_map_v3_map.png); summary_sha256=$(sha docs/archive/boundary_map/v3/reports/W_boundary_map_v3_summary_20260719.md); learning_runs_started=0; new_inference=R1prime-3_FM_dense_dial_2px_only"
  if ! commit_stage "R1P4" "complete" \
    "R1P-4: publish boundary map v3 measurements" \
    docs/issues.md \
    docs/experiments/boundary_map/tables/boundary_map_v3_metrics.csv \
    docs/archive/boundary_map/v3/tables/boundary_map_v3_ladder.csv \
    docs/experiments/boundary_map/tables/boundary_map_v3_confusion.csv \
    docs/experiments/boundary_map/tables/boundary_map_v3_conditional_targets.csv \
    docs/experiments/boundary_map/manifests/boundary_map_v3_manifest.json \
    docs/archive/boundary_map/v3/reports/W_boundary_map_v3_summary_20260719.md \
    docs/figs/boundary_map_v3 \
    "$MEASURE_REL"; then
    return 1
  fi
  R1P4_COMMIT="$LAST_COMMIT"
  write_status "R1prime-4" "complete" "commit=$R1P4_COMMIT"
}

record_ledger() {
  R1P12_COMMIT="$(state_get stages.R1P12.commit)"
  R1P3_COMMIT="$(state_get stages.R1P3.commit)"
  R1P4_COMMIT="$(state_get stages.R1P4.commit)"
  if [[ -z "$R1P12_COMMIT" || -z "$R1P3_COMMIT" || -z "$R1P4_COMMIT" ]]; then
    log "ledger stopped: one or more stage commit hashes are missing"
    return 1
  fi
  issue "R1P-20260719 commit ledger: R1P12_commit=$R1P12_COMMIT; R1P3_commit=$R1P3_COMMIT; R1P4_commit=$R1P4_COMMIT; learning_runs_started=0; allowed_new_inference=R1prime-3_FM_dense_dial_2px_only"
  if ! commit_stage "LEDGER" "complete" \
    "R1P-LEDGER: record boundary-map-v3 commits and hashes" \
    docs/issues.md; then
    return 1
  fi
  write_status "R1prime-1-4" "complete" \
    "all stages committed; ledger=$LAST_COMMIT"
}

main() {
  if ! acquire_driver_lock; then
    exit 1
  fi
  log "driver start learning_runs_started=0 allowed_new_inference=R1prime-3_FM_dense_dial_2px_only"
  if ! state_init || ! verify_state_history; then
    write_status "driver-state" "failed" "persistent state validation stopped execution"
    exit 1
  fi
  if ! preflight; then
    write_status "preflight" "failed" "start gate stopped execution"
    exit 1
  fi
  if ! recover_committed_stages || ! verify_state_history; then
    write_status "driver-state" "failed" "commit/push recovery stopped execution"
    exit 1
  fi
  local stage_status
  stage_status="$(state_get stages.R1P12.status)"
  if [[ "$stage_status" == "complete" ]]; then
    R1P12_COMMIT="$(state_get stages.R1P12.commit)"
    if [[ ! -f "$MEASURE/fm_dense_jobs.json" ]]; then
      write_status "R1prime-1-2" "failed" \
        "state is complete but FM job inventory is missing"
      exit 1
    fi
    if [[ -z "$(state_get job_sha256)" ]]; then
      state_set_job_sha "$(sha "$MEASURE/fm_dense_jobs.json")"
    elif [[ "$(state_get job_sha256)" != "$(sha "$MEASURE/fm_dense_jobs.json")" ]]; then
      write_status "R1prime-1-2" "failed" \
        "persisted FM job fingerprint differs from file"
      exit 1
    fi
    log "resume skip R1P12 commit=$R1P12_COMMIT"
  elif [[ "$stage_status" == "hard_error" ]]; then
    write_status "R1prime-1-2" "failed" \
      "persistent state records hard_error"
    exit 1
  elif ! run_r1p12; then
    write_status "R1prime-1-2" "partial" "outputs committed where present"
    exit 1
  fi
  stage_status="$(state_get stages.R1P3.status)"
  if [[ "$stage_status" =~ ^(complete|budget_exhausted|prerequisite_partial|measurement_partial)$ ]]; then
    R1P3_COMMIT="$(state_get stages.R1P3.commit)"
    log "resume skip R1P3 status=$stage_status commit=$R1P3_COMMIT"
  elif [[ "$stage_status" == "hard_error" ]]; then
    local preserved_mode
    preserved_mode="$(fm_result_mode)"
    if [[ "$preserved_mode" =~ ^(complete|budget_exhausted|prerequisite_partial|measurement_partial)$ ]]; then
      log "resume retry R1P3 from preserved measurements mode=$preserved_mode"
      if ! run_r1p3; then
        write_status "R1prime-3" "partial" \
          "preserved FM rows recommitted where present; finalize not run"
        exit 1
      fi
    else
      write_status "R1prime-3" "failed" \
        "persistent state records hard_error without recoverable FM manifest"
      exit 1
    fi
  elif ! run_r1p3; then
    write_status "R1prime-3" "partial" \
      "completed FM rows committed; finalize not run"
    exit 1
  fi
  stage_status="$(state_get stages.R1P4.status)"
  if [[ "$stage_status" == "complete" ]]; then
    R1P4_COMMIT="$(state_get stages.R1P4.commit)"
    log "resume skip R1P4 commit=$R1P4_COMMIT"
  elif [[ "$stage_status" == "hard_error" ]]; then
    write_status "R1prime-4" "failed" \
      "persistent state records hard_error"
    exit 1
  elif ! run_r1p4; then
    write_status "R1prime-4" "partial" "outputs committed where present"
    exit 1
  fi
  stage_status="$(state_get stages.LEDGER.status)"
  if [[ "$stage_status" == "complete" ]]; then
    write_status "R1prime-1-4" "complete" \
      "all stages and ledger already committed"
    log "resume found completed ledger commit=$(state_get stages.LEDGER.commit)"
  elif [[ "$stage_status" == "hard_error" ]]; then
    write_status "R1prime-1-4" "failed" \
      "persistent ledger state records hard_error"
    exit 1
  elif ! record_ledger; then
    write_status "R1prime-1-4" "partial" "ledger commit or push failed"
    exit 1
  fi
  log "driver complete head=$(git rev-parse HEAD)"
}

main "$@"
