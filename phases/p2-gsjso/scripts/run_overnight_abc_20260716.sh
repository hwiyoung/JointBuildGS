#!/usr/bin/env bash
# Detached A -> B -> C learning-zero measurement driver for the 2026-07-16 order.
# Launch:
#   setsid nohup bash phases/p2-gsjso/scripts/run_overnight_abc_20260716.sh \
#     > phases/p2-gsjso/runs/20260716_overnight_abc/detached.log 2>&1 < /dev/null &
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO" || exit 1

RUN_REL="phases/p2-gsjso/runs/20260716_overnight_abc"
RUN="$REPO/$RUN_REL"
LOG_DIR="$RUN/logs"
STATUS="$RUN/status.json"
ISSUES="$REPO/docs/issues.md"
BRANCH="exp/3b-surface-restore-corrected"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
DEV_IMAGE="jointbuildgs:dev"
MAST3R_IMAGE="jointbuildgs-s3ap-mast3r:20260714-f5209af"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
MODEL_REVISION="06e7259f34c3060f322df5cb0c7b9094f57e41fc"
MODEL_REPO_HOST="/home/innopam/.cache/huggingface/hub/models--naver--MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric"
MODEL_HOST="$MODEL_REPO_HOST/snapshots/$MODEL_REVISION"
MODEL_REPO_CONTAINER="/models/mast3r_metric"
MODEL_CONTAINER="$MODEL_REPO_CONTAINER/snapshots/$MODEL_REVISION"
UID_GID="$(id -u):$(id -g)"
START_EPOCH="$(date +%s)"

mkdir -p "$LOG_DIR"

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
    "wave": wave,
    "state": state,
    "detail": detail,
    "elapsed_seconds": time.time() - started,
    "learning_runs_started": 0,
}, ensure_ascii=False, indent=2))
PY
  mv "$temporary" "$STATUS"
}

run_tools() {
  docker run --rm -i \
    --user "$UID_GID" \
    -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e XDG_CACHE_HOME=/tmp \
    -v "$REPO:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    "$TOOLS_IMAGE" "$@"
}

run_dev() {
  docker run --rm -i \
    --user "$UID_GID" \
    -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e XDG_CACHE_HOME=/tmp \
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
  issue "OVN-ABC push failed after 3 attempts; branch=$BRANCH head=$(git rev-parse HEAD)"
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
  if ! git commit -m "$message"; then
    issue "$message commit failed"
    return 1
  fi
  push_retry
}

preflight() {
  write_status "preflight" "running" "checking committed branch, images, and learning-zero guard"
  local active_branch
  active_branch="$(git branch --show-current)"
  if [[ "$active_branch" != "$BRANCH" ]]; then
    issue "OVN-ABC preflight stopped: branch=$active_branch expected=$BRANCH"
    return 1
  fi
  git fetch origin "$BRANCH" > "$LOG_DIR/git_fetch.log" 2>&1 || {
    issue "OVN-ABC preflight stopped: git fetch failed; see $RUN_REL/logs/git_fetch.log"
    return 1
  }
  if [[ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$BRANCH")" ]]; then
    issue "OVN-ABC preflight stopped: local HEAD differs from origin/$BRANCH"
    return 1
  fi
  if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    issue "OVN-ABC preflight stopped: tracked worktree changes present"
    return 1
  fi
  if pgrep -af "train.py|src.stage2.train|e5_c001.*train|runner.*train" > "$LOG_DIR/learning_process_guard.log"; then
    issue "OVN-ABC preflight stopped: learning-like process found; see $RUN_REL/logs/learning_process_guard.log"
    return 1
  fi
  local image
  for image in "$TOOLS_IMAGE" "$DEV_IMAGE" "$MAST3R_IMAGE" "$ROOFER_IMAGE"; do
    docker image inspect "$image" > /dev/null 2>&1 || {
      issue "OVN-ABC preflight stopped: Docker image missing: $image"
      return 1
    }
  done
  if [[ ! -f "$MODEL_HOST/model.safetensors" ]]; then
    issue "OVN-ABC preflight stopped: MASt3R weight missing at $MODEL_HOST"
    return 1
  fi
  if [[ "$(sha "$MODEL_HOST/model.safetensors")" != "0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb" ]]; then
    issue "OVN-ABC preflight stopped: MASt3R weight SHA256 mismatch"
    return 1
  fi
  log "preflight complete head=$(git rev-parse HEAD) branch=$BRANCH learning_runs_started=0"
  write_status "preflight" "complete" "all guards passed"
}

run_a() {
  write_status "A" "running" "C001 exhaustive assembled-CityJSON rescore"
  log "A start"
  if ! run_tools python3 phases/p2-gsjso/scripts/overnight_qs_rescore.py \
    > "$LOG_DIR/A_qs_rescore.log" 2>&1; then
    issue "OVN-A execution failed; see $RUN_REL/logs/A_qs_rescore.log"
    write_status "A" "failed" "rescore command failed"
    return 1
  fi
  if ! run_tools python3 - <<'PY' > "$LOG_DIR/A_qa.log" 2>&1
import csv
import json
from pathlib import Path

paths = [
    Path("docs/qs_rescore_inventory.csv"),
    Path("docs/qs_rescore_scores.csv"),
    Path("docs/qs_rescore_pairs.csv"),
    Path("docs/qs_rescore_summary.csv"),
    Path("docs/figs/qs_rescore/qs_rescore_face_count_scatter.png"),
    Path("docs/figs/qs_rescore/qs_rescore_rms_pairs.png"),
    Path("docs/figs/qs_rescore/qs_rescore_topview_examples.png"),
    Path("phases/p2-gsjso/runs/20260716_qs_rescore/manifest.json"),
]
missing = [str(path) for path in paths if not path.is_file()]
if missing:
    raise SystemExit(f"missing outputs: {missing}")
for path in paths[:4]:
    rows = list(csv.DictReader(path.open()))
    if not rows or any(row.get("learning_runs_started") != "0" for row in rows):
        raise SystemExit(f"learning/cardinality QA failed: {path}")
manifest = json.loads(paths[-1].read_text())
if manifest["learning_runs_started"] != 0 or manifest["new_inference_runs"] != 0:
    raise SystemExit("manifest learning/inference drift")
print({
    "inventory_rows": sum(1 for _ in csv.DictReader(paths[0].open())),
    "score_rows": sum(1 for _ in csv.DictReader(paths[1].open())),
    "pair_rows": sum(1 for _ in csv.DictReader(paths[2].open())),
})
PY
  then
    issue "OVN-A QA failed; see $RUN_REL/logs/A_qa.log"
    write_status "A" "failed" "output QA failed"
    return 1
  fi
  issue "OVN-A measurement complete: manifest_sha256=$(sha phases/p2-gsjso/runs/20260716_qs_rescore/manifest.json); inventory_sha256=$(sha docs/qs_rescore_inventory.csv); pairs_sha256=$(sha docs/qs_rescore_pairs.csv); learning_runs_started=0"
  if ! commit_paths \
    "OVN-A: rescore C001 quality inventory" \
    docs/issues.md \
    docs/qs_rescore_inventory.csv \
    docs/qs_rescore_scores.csv \
    docs/qs_rescore_pairs.csv \
    docs/qs_rescore_summary.csv \
    docs/figs/qs_rescore \
    phases/p2-gsjso/runs/20260716_qs_rescore; then
    write_status "A" "partial" "outputs complete; commit or push failed"
    return 1
  fi
  A_COMMIT="$(git rev-parse HEAD)"
  issue "OVN-A commit ledger: commit=$A_COMMIT; manifest_sha256=$(sha phases/p2-gsjso/runs/20260716_qs_rescore/manifest.json)"
  write_status "A" "complete" "commit=$A_COMMIT"
  log "A complete commit=$A_COMMIT"
}

run_roofer_density() {
  local label="$1"
  local input="phases/p2-gsjso/runs/20260716_genclose_flat_density/roofer_inputs/flat_density_${label}.laz"
  local roofprint="phases/p2-gsjso/runs/20260716_genclose_flat_density/roofer_inputs/flat_density_${label}.geojson"
  local output="phases/p2-gsjso/runs/20260716_genclose_flat_density/roofer/${label}"
  mkdir -p "$output"
  if compgen -G "$output/*.city.jsonl" > /dev/null; then
    log "B Roofer $label resume: existing CityJSONSeq retained"
    return 0
  fi
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
    > "$LOG_DIR/B_roofer_${label}.log" 2>&1
}

run_b() {
  write_status "B" "running" "flat seed score and density-only canonical Roofer sweep"
  log "B start"
  if ! run_tools python3 phases/p2-gsjso/scripts/overnight_genclose.py prepare \
    > "$LOG_DIR/B_prepare.log" 2>&1; then
    issue "OVN-B prepare failed; see $RUN_REL/logs/B_prepare.log"
    write_status "B" "failed" "prepare command failed"
    return 1
  fi
  local label
  local roofer_failed=0
  for label in g0500 g0250 g0125; do
    if ! run_roofer_density "$label"; then
      roofer_failed=1
      issue "OVN-B Roofer failed for density=$label; see $RUN_REL/logs/B_roofer_${label}.log"
    fi
  done
  if [[ "$roofer_failed" -ne 0 ]]; then
    write_status "B" "partial" "one or more canonical Roofer calls failed"
    return 1
  fi
  if ! run_tools python3 phases/p2-gsjso/scripts/overnight_genclose.py finalize \
    > "$LOG_DIR/B_finalize.log" 2>&1; then
    issue "OVN-B finalize failed; see $RUN_REL/logs/B_finalize.log"
    write_status "B" "failed" "finalize command failed"
    return 1
  fi
  if ! run_tools python3 - <<'PY' > "$LOG_DIR/B_qa.log" 2>&1
import csv
import json
from pathlib import Path

score = list(csv.DictReader(Path("docs/genclose_flat_seed_scores.csv").open()))
assembly = list(csv.DictReader(Path("docs/genclose_density_assembly.csv").open()))
direct = list(csv.DictReader(Path("docs/genclose_direct_plane.csv").open()))
if len(assembly) != 9:
    raise SystemExit(f"assembly rows={len(assembly)} != 9")
for rows, name in [(score, "score"), (assembly, "assembly"), (direct, "direct")]:
    if not rows or any(row.get("learning_runs_started") != "0" for row in rows):
        raise SystemExit(f"{name} learning/cardinality QA failed")
manifest = json.loads(Path("phases/p2-gsjso/runs/20260716_genclose_flat_density/manifest.json").read_text())
if manifest["assembly_rows"] != 9 or manifest["learning_runs_started"] != 0:
    raise SystemExit("manifest QA failed")
figure = Path("docs/figs/genclose/genclose_density_assembly_topview.png")
if not figure.is_file():
    raise SystemExit("missing density figure")
print({"score_rows": len(score), "assembly_rows": len(assembly), "direct_rows": len(direct)})
PY
  then
    issue "OVN-B QA failed; see $RUN_REL/logs/B_qa.log"
    write_status "B" "failed" "output QA failed"
    return 1
  fi
  issue "OVN-B measurement complete: manifest_sha256=$(sha phases/p2-gsjso/runs/20260716_genclose_flat_density/manifest.json); flat_score_sha256=$(sha docs/genclose_flat_seed_scores.csv); assembly_sha256=$(sha docs/genclose_density_assembly.csv); learning_runs_started=0"
  if ! commit_paths \
    "OVN-B: measure flat-seed density assembly" \
    docs/issues.md \
    docs/genclose_flat_seed_scores.csv \
    docs/genclose_density_assembly.csv \
    docs/genclose_direct_plane.csv \
    docs/figs/genclose \
    phases/p2-gsjso/runs/20260716_genclose_flat_density; then
    write_status "B" "partial" "outputs complete; commit or push failed"
    return 1
  fi
  B_COMMIT="$(git rev-parse HEAD)"
  issue "OVN-B commit ledger: commit=$B_COMMIT; manifest_sha256=$(sha phases/p2-gsjso/runs/20260716_genclose_flat_density/manifest.json)"
  write_status "B" "complete" "commit=$B_COMMIT"
  log "B complete commit=$B_COMMIT"
}

run_c() {
  write_status "C" "running" "178-building boundary metrics and MASt3R queue"
  log "C start"
  if ! run_dev python3 phases/p2-gsjso/scripts/overnight_boundary_map.py prepare \
    > "$LOG_DIR/C_prepare.log" 2>&1; then
    issue "OVN-C prepare failed; see $RUN_REL/logs/C_prepare.log"
    write_status "C" "failed" "prepare command failed"
    return 1
  fi

  local gpu_rc=0
  timeout --signal=TERM --kill-after=60s 12h \
    docker run --rm \
      --user "$UID_GID" \
      --gpus device=0 \
      -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e XDG_CACHE_HOME=/tmp \
      -v "$REPO:/workspace/JointBuildGS" \
      -v "$MODEL_REPO_HOST:$MODEL_REPO_CONTAINER:ro" \
      -w /workspace/JointBuildGS \
      "$MAST3R_IMAGE" \
      python3 phases/p2-gsjso/scripts/overnight_boundary_mast3r.py \
        --model-dir "$MODEL_CONTAINER" --device cuda --max-seconds 43100 \
      > "$LOG_DIR/C_mast3r.log" 2>&1 || gpu_rc=$?
  if [[ "$gpu_rc" -ne 0 ]]; then
    issue "OVN-C MASt3R queue exited rc=$gpu_rc; partial rows retained and 2-wave list reserved; see $RUN_REL/logs/C_mast3r.log"
  fi

  if ! run_dev python3 phases/p2-gsjso/scripts/overnight_boundary_map.py finalize \
    > "$LOG_DIR/C_finalize.log" 2>&1; then
    issue "OVN-C finalize failed; see $RUN_REL/logs/C_finalize.log"
    write_status "C" "failed" "finalize command failed"
    return 1
  fi
  if ! run_dev python3 - <<'PY' > "$LOG_DIR/C_qa.log" 2>&1
import csv
import json
from pathlib import Path

metrics = list(csv.DictReader(Path("docs/boundary_map_metrics.csv").open()))
ladder = list(csv.DictReader(Path("docs/boundary_map_ladder.csv").open()))
confusion = list(csv.DictReader(Path("docs/boundary_map_confusion.csv").open()))
cases = list(csv.DictReader(Path("docs/boundary_map_boundary_cases.csv").open()))
if len(metrics) != 178 or len(ladder) != 178:
    raise SystemExit(f"population drift metrics={len(metrics)} ladder={len(ladder)}")
if not confusion or not (10 <= len(cases) <= 20):
    raise SystemExit(f"confusion/cases QA failed: {len(confusion)} {len(cases)}")
for rows, name in [(metrics, "metrics"), (ladder, "ladder"), (confusion, "confusion"), (cases, "cases")]:
    if any(row.get("learning_runs_started") != "0" for row in rows):
        raise SystemExit(f"{name} learning flag drift")
manifest = json.loads(Path("docs/boundary_map_manifest.json").read_text())
if manifest["evaluation_population"] != 178 or manifest["learning_runs_started"] != 0:
    raise SystemExit("manifest QA failed")
if not Path("docs/figs/boundary_map/boundary_map_ladder.png").is_file():
    raise SystemExit("map figure missing")
print({
    "metrics_rows": len(metrics),
    "ladder_rows": len(ladder),
    "confusion_rows": len(confusion),
    "second_wave": len(manifest["second_wave_buildings"]),
})
PY
  then
    issue "OVN-C QA failed; see $RUN_REL/logs/C_qa.log"
    write_status "C" "failed" "output QA failed"
    return 1
  fi
  issue "OVN-C measurement complete: manifest_sha256=$(sha docs/boundary_map_manifest.json); metrics_sha256=$(sha docs/boundary_map_metrics.csv); ladder_sha256=$(sha docs/boundary_map_ladder.csv); learning_runs_started=0; new_inference=MASt3R_correspondence_only"
  if ! commit_paths \
    "OVN-C: measure 178-building boundary map" \
    docs/issues.md \
    docs/boundary_map_metrics.csv \
    docs/boundary_map_ladder.csv \
    docs/boundary_map_confusion.csv \
    docs/boundary_map_boundary_cases.csv \
    docs/boundary_map_manifest.json \
    docs/figs/boundary_map \
    phases/p2-gsjso/runs/20260716_boundary_map; then
    write_status "C" "partial" "outputs complete; commit or push failed"
    return 1
  fi
  C_COMMIT="$(git rev-parse HEAD)"
  issue "OVN-C commit ledger: commit=$C_COMMIT; manifest_sha256=$(sha docs/boundary_map_manifest.json)"
  write_status "C" "complete" "commit=$C_COMMIT"
  log "C complete commit=$C_COMMIT"
}

finalize_ledger() {
  issue "OVN-D skipped: optional cheap-refine pilot not started after the serial A-B-C overnight budget."
  issue "OVN-ABC driver ledger: prep_commit=$PREP_COMMIT; A_commit=${A_COMMIT:-none}; B_commit=${B_COMMIT:-none}; C_commit=${C_COMMIT:-none}; learning_runs_started=0."
  write_status "ABC" "complete" "A=${A_COMMIT:-none} B=${B_COMMIT:-none} C=${C_COMMIT:-none}; D=skipped_optional"
  commit_paths \
    "OVN-ABC: record overnight commit ledger" \
    docs/issues.md \
    "$RUN_REL/status.json"
}

main() {
  PREP_COMMIT="$(git rev-parse HEAD)"
  A_COMMIT=""
  B_COMMIT=""
  C_COMMIT=""
  log "overnight driver start prep_commit=$PREP_COMMIT"
  if ! preflight; then
    write_status "preflight" "failed" "driver stopped"
    exit 1
  fi

  local a_rc=0
  local b_rc=0
  local c_rc=0
  run_a || a_rc=$?
  if [[ "$a_rc" -eq 0 ]]; then
    run_b || b_rc=$?
  else
    issue "OVN-B not started because serial predecessor A did not complete"
    b_rc=1
  fi
  if [[ "$b_rc" -eq 0 ]]; then
    run_c || c_rc=$?
  else
    issue "OVN-C not started because serial predecessor B did not complete"
    c_rc=1
  fi
  finalize_ledger
  log "overnight driver finish A_rc=$a_rc B_rc=$b_rc C_rc=$c_rc"
  if [[ "$a_rc" -ne 0 || "$b_rc" -ne 0 || "$c_rc" -ne 0 ]]; then
    exit 1
  fi
}

main "$@"
