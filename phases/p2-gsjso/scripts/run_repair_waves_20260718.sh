#!/usr/bin/env bash
# Detached learning-zero R1 -> R2 -> R3 -> R4 measurement driver.
# Launch from the repository root:
#   setsid nohup bash phases/p2-gsjso/scripts/run_repair_waves_20260718.sh \
#     > phases/p2-gsjso/runs/20260718_repair_waves/detached.log 2>&1 < /dev/null &
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO" || exit 1

RUN_REL="phases/p2-gsjso/runs/20260718_repair_waves"
RUN="$REPO/$RUN_REL"
LOG_DIR="$RUN/logs"
STATUS="$RUN/status.json"
ISSUES="$REPO/docs/issues.md"
BRANCH="exp/3b-surface-restore-corrected"

TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
DEV_IMAGE="jointbuildgs:dev"
MAST3R_IMAGE="jointbuildgs-s3ap-mast3r:20260714-f5209af"
MAST3R_IMAGE_ID="sha256:89d64b4c7112cc55db0d42d562e2a0208858658c0c67ab1bd48424175c50f501"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
MODEL_REVISION="06e7259f34c3060f322df5cb0c7b9094f57e41fc"
MODEL_SHA256="0a615eb05fa9db654050aa655945ee5696e7c6c1b7f93f1ee8c37249010f6feb"
MODEL_REPO_HOST="/home/innopam/.cache/huggingface/hub/models--naver--MASt3R_ViTLarge_BaseDecoder_512_catmlpdpt_metric"
MODEL_HOST="$MODEL_REPO_HOST/snapshots/$MODEL_REVISION"
MODEL_REPO_CONTAINER="/models/mast3r_metric"
MODEL_CONTAINER="$MODEL_REPO_CONTAINER/snapshots/$MODEL_REVISION"
UID_GID="$(id -u):$(id -g)"
START_EPOCH="$(date +%s)"
R1_TOTAL_BUDGET_SECONDS=21600
R1_CROP_MAX_SECONDS=3600

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

run_mast3r_queue() {
  local mode="$1"
  local seconds="$2"
  timeout --signal=TERM --kill-after=60s "${seconds}s" \
    docker run --rm \
      --user "$UID_GID" \
      --gpus device=0 \
      -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e XDG_CACHE_HOME=/tmp \
      -e MAST3R_DOCKER_IMAGE_ID="$MAST3R_IMAGE_ID" \
      -v "$REPO:/workspace/JointBuildGS" \
      -v "$MODEL_REPO_HOST:$MODEL_REPO_CONTAINER:ro" \
      -w /workspace/JointBuildGS \
      "$MAST3R_IMAGE" \
      python3 phases/p2-gsjso/scripts/boundary_map_v2_mast3r.py "$mode" \
        --model-dir "$MODEL_CONTAINER" \
        --device cuda \
        --max-seconds "$seconds"
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
  issue "RW-20260718 push attempts exhausted: branch=$BRANCH head=$(git rev-parse HEAD)"
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
    issue "$message commit command exited nonzero"
    return 1
  fi
  push_retry
}

preflight() {
  write_status "preflight" "running" "branch, origin, process, image, model, and GPU checks"
  local active_branch
  active_branch="$(git branch --show-current)"
  if [[ "$active_branch" != "$BRANCH" ]]; then
    issue "RW-20260718 preflight stopped: branch=$active_branch expected=$BRANCH"
    return 1
  fi
  if ! git fetch origin "$BRANCH" > "$LOG_DIR/git_fetch.log" 2>&1; then
    issue "RW-20260718 preflight stopped: git fetch exited nonzero; log=$RUN_REL/logs/git_fetch.log"
    return 1
  fi
  if [[ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$BRANCH")" ]]; then
    issue "RW-20260718 preflight stopped: local HEAD differs from origin/$BRANCH"
    return 1
  fi
  if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    issue "RW-20260718 preflight stopped: tracked worktree changes present"
    return 1
  fi
  if pgrep -af "train.py|src.stage2.train|e5_c001.*train|runner.*train" \
    > "$LOG_DIR/learning_process_guard.log"; then
    issue "RW-20260718 preflight stopped: learning-like process listed in $RUN_REL/logs/learning_process_guard.log"
    return 1
  fi
  local image
  for image in "$TOOLS_IMAGE" "$DEV_IMAGE" "$MAST3R_IMAGE" "$ROOFER_IMAGE"; do
    if ! docker image inspect "$image" > /dev/null 2>&1; then
      issue "RW-20260718 preflight stopped: Docker image missing: $image"
      return 1
    fi
  done
  if [[ "$(docker image inspect --format '{{.Id}}' "$MAST3R_IMAGE")" != "$MAST3R_IMAGE_ID" ]]; then
    issue "RW-20260718 preflight stopped: MASt3R Docker image ID mismatch"
    return 1
  fi
  if [[ ! -f "$MODEL_HOST/model.safetensors" ]]; then
    issue "RW-20260718 preflight stopped: MASt3R weight file missing"
    return 1
  fi
  if [[ "$(sha "$MODEL_HOST/model.safetensors")" != "$MODEL_SHA256" ]]; then
    issue "RW-20260718 preflight stopped: MASt3R weight SHA256 mismatch"
    return 1
  fi
  if ! docker run --rm --gpus device=0 "$MAST3R_IMAGE" \
    nvidia-smi --query-gpu=name --format=csv,noheader \
    > "$LOG_DIR/gpu_preflight.log" 2>&1; then
    issue "RW-20260718 preflight stopped: GPU container check exited nonzero"
    return 1
  fi
  log "preflight complete head=$(git rev-parse HEAD) learning_runs_started=0"
  write_status "preflight" "complete" "all start gates passed"
}

r1_remaining_seconds() {
  local started="$1"
  local elapsed
  elapsed=$(( $(date +%s) - started ))
  local remaining=$(( R1_TOTAL_BUDGET_SECONDS - elapsed ))
  if (( remaining < 0 )); then
    remaining=0
  fi
  printf "%s" "$remaining"
}

run_r1() {
  write_status "R1" "running" "canonical 178, depth-2 rule, crop-pair 14, and FM queue"
  local r1_started
  r1_started="$(date +%s)"
  if ! run_dev python3 phases/p2-gsjso/scripts/boundary_map_v2.py prepare \
    > "$LOG_DIR/R1_prepare.log" 2>&1; then
    issue "RW-R1 prepare command exited nonzero; log=$RUN_REL/logs/R1_prepare.log"
    return 1
  fi
  if ! run_dev python3 phases/p2-gsjso/scripts/boundary_map_v2.py fit-primary \
    > "$LOG_DIR/R1_fit_primary.log" 2>&1; then
    issue "RW-R1 primary-rule command exited nonzero; log=$RUN_REL/logs/R1_fit_primary.log"
    return 1
  fi

  local remaining
  local crop_budget
  remaining="$(r1_remaining_seconds "$r1_started")"
  crop_budget="$remaining"
  if (( crop_budget > R1_CROP_MAX_SECONDS )); then
    crop_budget="$R1_CROP_MAX_SECONDS"
  fi
  if (( crop_budget > 0 )); then
    if ! run_mast3r_queue "crop-pair" "$crop_budget" \
      > "$LOG_DIR/R1_crop_pair.log" 2>&1; then
      issue "RW-R1 crop-pair queue exited nonzero; stale/crash guard stopped finalize; partial rows retained; log=$RUN_REL/logs/R1_crop_pair.log"
      return 1
    fi
  else
    issue "RW-R1 crop-pair queue not started: shared 21600-second R1 budget exhausted"
    return 1
  fi

  remaining="$(r1_remaining_seconds "$r1_started")"
  if (( remaining > 0 )); then
    if ! run_mast3r_queue "fm" "$remaining" \
      > "$LOG_DIR/R1_fm.log" 2>&1; then
      issue "RW-R1 FM queue exited nonzero; stale/crash guard stopped finalize; partial rows retained; log=$RUN_REL/logs/R1_fm.log"
      return 1
    fi
  else
    issue "RW-R1 FM queue not started: shared 21600-second R1 budget exhausted"
    return 1
  fi

  if ! run_dev python3 phases/p2-gsjso/scripts/boundary_map_v2.py finalize \
    > "$LOG_DIR/R1_finalize.log" 2>&1; then
    issue "RW-R1 finalize command exited nonzero; log=$RUN_REL/logs/R1_finalize.log"
    return 1
  fi
  if ! run_dev python3 - <<'PY' > "$LOG_DIR/R1_qa.log" 2>&1
import csv
import json
from pathlib import Path

docs = Path("docs")
metrics = list(csv.DictReader((docs / "boundary_map_v2_metrics.csv").open()))
ladder = list(csv.DictReader((docs / "boundary_map_v2_ladder.csv").open()))
confusion = list(csv.DictReader((docs / "boundary_map_v2_confusion.csv").open()))
cases = list(csv.DictReader((docs / "boundary_map_v2_boundary_cases.csv").open()))
targets = list(csv.DictReader((docs / "boundary_map_v2_conditional_targets.csv").open()))
crop = list(csv.DictReader(Path(
    "phases/p2-gsjso/runs/20260718_boundary_map_v2/crop_pair_results.csv"
).open()))
manifest = json.loads((docs / "boundary_map_v2_manifest.json").read_text())
if len(metrics) != 178 or len(ladder) != 178:
    raise SystemExit(f"R1 population drift metrics={len(metrics)} ladder={len(ladder)}")
repair_ids = {
    "DEBY_LOD2_104583447", "DEBY_LOD2_104586480",
    "DEBY_LOD2_108246888", "DEBY_LOD2_42364609",
    "DEBY_LOD2_4908023", "DEBY_LOD2_4908024",
    "DEBY_LOD2_4908025", "DEBY_LOD2_4908026",
    "DEBY_LOD2_4908027", "DEBY_LOD2_4908028",
    "DEBY_LOD2_4908166", "DEBY_LOD2_4908352",
    "DEBY_LOD2_4908354", "DEBY_LOD2_8568403",
}
projection_incomplete = set(
    manifest["population"].get("repair_projection_incomplete_buildings", [])
)
crop_ids = {row["building_id"] for row in crop}
if crop_ids & projection_incomplete:
    raise SystemExit("R1 crop/projection-incomplete identifier overlap")
if crop_ids | projection_incomplete != repair_ids:
    raise SystemExit("R1 repair crop-pair identifier set drift")
if projection_incomplete:
    raise SystemExit(
        "R1 repair projection incomplete: "
        f"{sorted(projection_incomplete)}"
    )
crop_incomplete = {
    row["building_id"]: row.get("status", "")
    for row in crop
    if row.get("status") != "complete"
}
if crop_incomplete:
    raise SystemExit(f"R1 repair crop-pair incomplete: {crop_incomplete}")
if any(row.get("learning_runs_started") != "0" for rows in
       (metrics, ladder, confusion, cases, targets) for row in rows):
    raise SystemExit("R1 learning flag drift")
metric_rows = [
    row for row in confusion
    if row.get("record_type") == "validation_metric"
    and row.get("comparison") == "manual_rule_vs_constant_well_textured"
]
if len(metric_rows) != 1 or metric_rows[0].get("n_records") != "22":
    raise SystemExit("R1 validation/constant comparison row missing")
if manifest.get("learning_runs_started") != 0:
    raise SystemExit("R1 manifest learning flag drift")
checks = manifest["population"]["population_checks"]
if checks["raw_lidar_population"] != 199 or checks["raw_lidar_assembled_true"] != 178:
    raise SystemExit("R1 canonical population check drift")
if checks["dense_success_in_canonical"] != 114 or checks["dense_failure_in_canonical"] != 64:
    raise SystemExit("R1 dense 114/64 check drift")
if manifest["population"]["symmetric_difference_count"] != 42:
    raise SystemExit("R1 symmetric difference drift")
if manifest.get("incomplete_crop_pair_buildings"):
    raise SystemExit(
        "R1 manifest crop-pair incomplete: "
        f"{manifest['incomplete_crop_pair_buildings']}"
    )
if manifest.get("fm_incomplete_buildings"):
    raise SystemExit(
        f"R1 manifest FM incomplete: {manifest['fm_incomplete_buildings']}"
    )
allowed = {
    "none; frozen 20260716 crop-pair reused",
    "R1-2 MASt3R crop-pair correspondence only",
    "R1-4 FM fixed-pose retriangulation only",
    "R1-2 MASt3R crop-pair correspondence only; R1-4 FM fixed-pose retriangulation only",
}
if any(row.get("new_inference_type") not in allowed for row in metrics):
    raise SystemExit("R1 new-inference type drift")
if any(row["assignment"] not in {
    "textureless_correspondence_anchored", "outline_only"
} for row in targets):
    raise SystemExit("R1 conditional target assignment drift")
for path in (
    docs / "boundary_map_v2_metrics.csv",
    docs / "boundary_map_v2_ladder.csv",
    docs / "boundary_map_v2_confusion.csv",
    docs / "boundary_map_v2_boundary_cases.csv",
    docs / "boundary_map_v2_manifest.json",
    docs / "figs/boundary_map_v2/boundary_map_v2_ladder.png",
    docs / "W_boundary_map_v2_summary_20260718.md",
):
    if not path.is_file():
        raise SystemExit(f"R1 output missing: {path}")
print({
    "metrics": len(metrics),
    "crop_pair": len(crop),
    "conditional_targets": len(targets),
    "fm_incomplete": len(manifest.get("fm_incomplete_buildings", [])),
})
PY
  then
    issue "RW-R1 QA command exited nonzero; log=$RUN_REL/logs/R1_qa.log"
    return 1
  fi
  issue "RW-R1 measurement complete: metrics_sha256=$(sha docs/boundary_map_v2_metrics.csv); ladder_sha256=$(sha docs/boundary_map_v2_ladder.csv); manifest_sha256=$(sha docs/boundary_map_v2_manifest.json); figure_sha256=$(sha docs/figs/boundary_map_v2/boundary_map_v2_ladder.png); learning_runs_started=0; new_inference=R1-2_crop_pair_and_R1-4_FM_only"
  if ! commit_paths \
    "RW-R1: rebuild canonical boundary map v2" \
    docs/issues.md \
    docs/boundary_map_v2_metrics.csv \
    docs/boundary_map_v2_ladder.csv \
    docs/boundary_map_v2_confusion.csv \
    docs/boundary_map_v2_boundary_cases.csv \
    docs/boundary_map_v2_conditional_targets.csv \
    docs/boundary_map_v2_manifest.json \
    docs/W_boundary_map_v2_summary_20260718.md \
    docs/figs/boundary_map_v2 \
    phases/p2-gsjso/runs/20260718_boundary_map_v2; then
    return 1
  fi
  R1_COMMIT="$(git rev-parse HEAD)"
  write_status "R1" "complete" "commit=$R1_COMMIT"
  log "R1 complete commit=$R1_COMMIT"
}

run_r2() {
  write_status "R2" "running" "2813-row completeness backfill and 10x4 panel"
  if ! run_tools python3 phases/p2-gsjso/scripts/qs_rescore_completeness_panel.py \
    > "$LOG_DIR/R2_run.log" 2>&1; then
    issue "RW-R2 execution command exited nonzero; log=$RUN_REL/logs/R2_run.log"
    return 1
  fi
  if ! run_tools python3 - <<'PY' > "$LOG_DIR/R2_qa.log" 2>&1
import csv
import json
import math
from pathlib import Path

scores = list(csv.DictReader(Path("docs/qs_rescore_scores.csv").open()))
panel = list(csv.DictReader(Path("docs/qs_rescore_topview_panel.csv").open()))
spot = list(csv.DictReader(Path("docs/qs_rescore_hausdorff_spotcheck.csv").open()))
manifest = json.loads(Path(
    "phases/p2-gsjso/runs/20260718_qs_rescore_completeness_panel/manifest.json"
).read_text())
if len(scores) != 2813 or len(panel) != 40 or len(spot) != 12:
    raise SystemExit(
        f"R2 cardinality drift scores={len(scores)} panel={len(panel)} spot={len(spot)}"
    )
values = [float(row["roof_completeness"]) for row in scores]
if not all(math.isfinite(value) and 0 <= value <= 1 for value in values):
    raise SystemExit("R2 roof_completeness domain drift")
refs = [row for row in scores if row["role"] == "reference"]
if len(refs) != 18 or any(float(row["roof_completeness"]) != 1.0 for row in refs):
    raise SystemExit("R2 reference completeness self-check drift")
if any(row.get("learning_runs_started") != "0" for row in scores):
    raise SystemExit("R2 score learning flag drift")
for rows in (panel, spot):
    if any(
        row.get("learning_runs_started") != "0"
        or row.get("new_inference_runs") != "0"
        for row in rows
    ):
        raise SystemExit("R2 output learning/inference flag drift")
if manifest["learning_runs_started"] != 0 or manifest["new_inference_runs"] != 0:
    raise SystemExit("R2 manifest learning/inference flag drift")
if manifest["dense_success_building_count"] != 10:
    raise SystemExit("R2 dense-success population drift")
for path in (
    Path("docs/figs/qs_rescore/qs_rescore_topview_10x4.png"),
    Path("docs/W_qs_rescore_completeness_panel_20260718.md"),
):
    if not path.is_file():
        raise SystemExit(f"R2 output missing: {path}")
print({"scores": len(scores), "panel": len(panel), "spot": len(spot)})
PY
  then
    issue "RW-R2 QA command exited nonzero; log=$RUN_REL/logs/R2_qa.log"
    return 1
  fi
  issue "RW-R2 measurement complete: scores_sha256=$(sha docs/qs_rescore_scores.csv); panel_sha256=$(sha docs/qs_rescore_topview_panel.csv); spot_sha256=$(sha docs/qs_rescore_hausdorff_spotcheck.csv); manifest_sha256=$(sha phases/p2-gsjso/runs/20260718_qs_rescore_completeness_panel/manifest.json); figure_sha256=$(sha docs/figs/qs_rescore/qs_rescore_topview_10x4.png); learning_runs_started=0; new_inference_runs=0"
  if ! commit_paths \
    "RW-R2: add roof completeness and 10x4 panel" \
    docs/issues.md \
    docs/qs_rescore_scores.csv \
    docs/qs_rescore_topview_panel.csv \
    docs/qs_rescore_hausdorff_spotcheck.csv \
    docs/W_qs_rescore_completeness_panel_20260718.md \
    docs/figs/qs_rescore/qs_rescore_topview_10x4.png \
    phases/p2-gsjso/runs/20260718_qs_rescore_completeness_panel; then
    return 1
  fi
  R2_COMMIT="$(git rev-parse HEAD)"
  write_status "R2" "complete" "commit=$R2_COMMIT"
  log "R2 complete commit=$R2_COMMIT"
}

run_r3() {
  write_status "R3" "running" "canonical 178 dense, ALS, and reference rescore"
  if ! run_tools python3 phases/p2-gsjso/scripts/qs_baseline178_rescore.py \
    > "$LOG_DIR/R3_run.log" 2>&1; then
    issue "RW-R3 execution command exited nonzero; log=$RUN_REL/logs/R3_run.log"
    return 1
  fi
  if ! run_tools python3 - <<'PY' > "$LOG_DIR/R3_qa.log" 2>&1
import csv
import json
from collections import Counter
from pathlib import Path

scores = list(csv.DictReader(Path("docs/qs_baseline178_scores.csv").open()))
summary = list(csv.DictReader(Path("docs/qs_baseline178_summary.csv").open()))
manifest = json.loads(Path("docs/qs_baseline178_manifest.json").read_text())
roles = Counter(row["role"] for row in scores)
if len(scores) != 534 or roles != Counter({"dense": 178, "als": 178, "reference": 178}):
    raise SystemExit(f"R3 cardinality drift rows={len(scores)} roles={dict(roles)}")
if sum(row["role"] == "dense" and row["has_lod22"] == "true" for row in scores) != 114:
    raise SystemExit("R3 dense LoD2 count drift")
if sum(row["role"] == "als" and row["has_lod22"] == "true" for row in scores) != 178:
    raise SystemExit("R3 ALS LoD2 count drift")
refs = [row for row in scores if row["role"] == "reference"]
if any(float(row["roof_rms_m"]) != 0.0 or float(row["roof_completeness"]) != 1.0 for row in refs):
    raise SystemExit("R3 reference self-check drift")
if any(
    row["learning_runs_started"] != "0" or row["new_inference_runs"] != "0"
    for row in scores + summary
):
    raise SystemExit("R3 learning/inference flag drift")
agreement = [
    row for row in summary
    if row["row_type"] == "old_status_has_lod22_agreement"
]
if len(agreement) != 2 or any(float(row["status_agreement_rate"]) != 1.0 for row in agreement):
    raise SystemExit("R3 old status agreement drift")
if manifest["population_count"] != 178 or manifest["learning_runs_started"] != 0:
    raise SystemExit("R3 manifest population/learning drift")
if manifest["new_inference_runs"] != 0:
    raise SystemExit("R3 manifest inference drift")
if not Path("docs/figs/qs_baseline178/dense_vs_als_rms_distribution.png").is_file():
    raise SystemExit("R3 figure missing")
print({"scores": len(scores), "summary": len(summary), "roles": dict(roles)})
PY
  then
    issue "RW-R3 QA command exited nonzero; log=$RUN_REL/logs/R3_qa.log"
    return 1
  fi
  issue "RW-R3 measurement complete: scores_sha256=$(sha docs/qs_baseline178_scores.csv); summary_sha256=$(sha docs/qs_baseline178_summary.csv); manifest_sha256=$(sha docs/qs_baseline178_manifest.json); figure_sha256=$(sha docs/figs/qs_baseline178/dense_vs_als_rms_distribution.png); learning_runs_started=0; new_inference_runs=0"
  if ! commit_paths \
    "RW-R3: rescore canonical 178 dense and ALS baselines" \
    docs/issues.md \
    docs/qs_baseline178_scores.csv \
    docs/qs_baseline178_summary.csv \
    docs/qs_baseline178_manifest.json \
    docs/figs/qs_baseline178 \
    phases/p2-gsjso/runs/20260718_qs_baseline178_rescore; then
    return 1
  fi
  R3_COMMIT="$(git rev-parse HEAD)"
  write_status "R3" "complete" "commit=$R3_COMMIT"
  log "R3 complete commit=$R3_COMMIT"
}

run_r4() {
  write_status "R4" "running" "C001 18-building, 18-condition cheap-refinement grid"
  if ! python3 phases/p2-gsjso/scripts/qs_cheap_refine_sweep.py run \
    > "$LOG_DIR/R4_run.log" 2>&1; then
    issue "RW-R4 execution command exited nonzero; log=$RUN_REL/logs/R4_run.log"
    return 1
  fi
  if ! run_tools python3 - <<'PY' > "$LOG_DIR/R4_qa.log" 2>&1
import csv
import json
import math
from collections import Counter
from pathlib import Path

scores = list(csv.DictReader(Path("docs/qs_cheap_refine_sweep.csv").open()))
summary = list(csv.DictReader(Path("docs/qs_cheap_refine_sweep_summary.csv").open()))
manifest = json.loads(Path("docs/qs_cheap_refine_sweep_manifest.json").read_text())
if len(scores) != 324 or len(summary) != 18:
    raise SystemExit(f"R4 cardinality drift scores={len(scores)} summary={len(summary)}")
condition_counts = Counter(row["condition_id"] for row in scores)
if len(condition_counts) != 18 or set(condition_counts.values()) != {18}:
    raise SystemExit(f"R4 condition cardinality drift: {dict(condition_counts)}")
if any(
    row["learning_runs_started"] != "0" or row["new_inference_runs"] != "0"
    for row in scores + summary
):
    raise SystemExit("R4 learning/inference flag drift")
values = [float(row["roof_completeness"]) for row in scores]
if not all(math.isfinite(value) and 0 <= value <= 1 for value in values):
    raise SystemExit("R4 roof completeness domain drift")
if (
    manifest["population_count"] != 18
    or manifest["condition_count"] != 18
    or manifest["score_rows"] != 324
    or manifest["learning_runs_started"] != 0
    or manifest["new_inference_runs"] != 0
):
    raise SystemExit("R4 manifest QA drift")
if not Path("docs/figs/qs_cheap_refine_sweep/parameter_grid.png").is_file():
    raise SystemExit("R4 figure missing")
print({"scores": len(scores), "summary": len(summary), "conditions": len(condition_counts)})
PY
  then
    issue "RW-R4 QA command exited nonzero; log=$RUN_REL/logs/R4_qa.log"
    return 1
  fi
  issue "RW-R4 measurement complete: scores_sha256=$(sha docs/qs_cheap_refine_sweep.csv); summary_sha256=$(sha docs/qs_cheap_refine_sweep_summary.csv); manifest_sha256=$(sha docs/qs_cheap_refine_sweep_manifest.json); figure_sha256=$(sha docs/figs/qs_cheap_refine_sweep/parameter_grid.png); learning_runs_started=0; new_inference_runs=0"
  if ! commit_paths \
    "RW-R4: sweep C001 cheap-refinement parameters" \
    docs/issues.md \
    docs/qs_cheap_refine_sweep.csv \
    docs/qs_cheap_refine_sweep_summary.csv \
    docs/qs_cheap_refine_sweep_manifest.json \
    docs/figs/qs_cheap_refine_sweep \
    phases/p2-gsjso/runs/20260718_qs_cheap_refine_sweep; then
    return 1
  fi
  R4_COMMIT="$(git rev-parse HEAD)"
  write_status "R4" "complete" "commit=$R4_COMMIT"
  log "R4 complete commit=$R4_COMMIT"
}

commit_partial_r1() {
  commit_paths \
    "RW-R1-PARTIAL: preserve boundary map measurements" \
    docs/issues.md \
    docs/boundary_map_v2_metrics.csv \
    docs/boundary_map_v2_ladder.csv \
    docs/boundary_map_v2_confusion.csv \
    docs/boundary_map_v2_boundary_cases.csv \
    docs/boundary_map_v2_conditional_targets.csv \
    docs/boundary_map_v2_manifest.json \
    docs/W_boundary_map_v2_summary_20260718.md \
    docs/figs/boundary_map_v2 \
    phases/p2-gsjso/runs/20260718_boundary_map_v2
}

commit_partial_r2() {
  commit_paths \
    "RW-R2-PARTIAL: preserve completeness panel measurements" \
    docs/issues.md \
    docs/qs_rescore_scores.csv \
    docs/qs_rescore_topview_panel.csv \
    docs/qs_rescore_hausdorff_spotcheck.csv \
    docs/W_qs_rescore_completeness_panel_20260718.md \
    docs/figs/qs_rescore/qs_rescore_topview_10x4.png \
    phases/p2-gsjso/runs/20260718_qs_rescore_completeness_panel
}

commit_partial_r3() {
  commit_paths \
    "RW-R3-PARTIAL: preserve baseline 178 measurements" \
    docs/issues.md \
    docs/qs_baseline178_scores.csv \
    docs/qs_baseline178_summary.csv \
    docs/qs_baseline178_manifest.json \
    docs/figs/qs_baseline178 \
    phases/p2-gsjso/runs/20260718_qs_baseline178_rescore
}

commit_partial_r4() {
  commit_paths \
    "RW-R4-PARTIAL: preserve cheap-refinement sweep measurements" \
    docs/issues.md \
    docs/qs_cheap_refine_sweep.csv \
    docs/qs_cheap_refine_sweep_summary.csv \
    docs/qs_cheap_refine_sweep_manifest.json \
    docs/figs/qs_cheap_refine_sweep \
    phases/p2-gsjso/runs/20260718_qs_cheap_refine_sweep
}

finalize_ledger() {
  issue "RW-20260718 commit ledger: prep_commit=$PREP_COMMIT; R1_commit=${R1_COMMIT:-none}; R2_commit=${R2_COMMIT:-none}; R3_commit=${R3_COMMIT:-none}; R4_commit=${R4_COMMIT:-none}; R1_rc=$R1_RC; R2_rc=$R2_RC; R3_rc=$R3_RC; R4_rc=$R4_RC; learning_runs_started=0."
  issue "RW-20260718 artifact ledger: R1_manifest_sha256=$(sha docs/boundary_map_v2_manifest.json); R2_manifest_sha256=$(sha phases/p2-gsjso/runs/20260718_qs_rescore_completeness_panel/manifest.json); R3_manifest_sha256=$(sha docs/qs_baseline178_manifest.json); R4_manifest_sha256=$(sha docs/qs_cheap_refine_sweep_manifest.json)."
  if [[ "$R1_RC" -eq 0 && "$R2_RC" -eq 0 && "$R3_RC" -eq 0 && "$R4_RC" -eq 0 ]]; then
    write_status "R1-R4" "complete" "all four waves committed"
  else
    write_status "R1-R4" "partial" "R1=$R1_RC R2=$R2_RC R3=$R3_RC R4=$R4_RC"
  fi
  commit_paths \
    "RW-LEDGER: record repair-wave commits and hashes" \
    docs/issues.md
}

main() {
  PREP_COMMIT="$(git rev-parse HEAD)"
  R1_COMMIT=""
  R2_COMMIT=""
  R3_COMMIT=""
  R4_COMMIT=""
  R1_RC=0
  R2_RC=0
  R3_RC=0
  R4_RC=0
  log "repair-wave driver start prep_commit=$PREP_COMMIT"
  if ! preflight; then
    write_status "preflight" "failed" "driver stopped before measurements"
    exit 1
  fi

  if ! run_r1; then
    R1_RC=1
    issue "RW-R1 partial state recorded after nonzero wave result"
    commit_partial_r1 || true
    R1_COMMIT="$(git rev-parse HEAD)"
    write_status "R1" "partial" "commit=$R1_COMMIT"
  fi
  if ! run_r2; then
    R2_RC=1
    issue "RW-R2 partial state recorded after nonzero wave result"
    commit_partial_r2 || true
    R2_COMMIT="$(git rev-parse HEAD)"
    write_status "R2" "partial" "commit=$R2_COMMIT"
  fi
  if ! run_r3; then
    R3_RC=1
    issue "RW-R3 partial state recorded after nonzero wave result"
    commit_partial_r3 || true
    R3_COMMIT="$(git rev-parse HEAD)"
    write_status "R3" "partial" "commit=$R3_COMMIT"
  fi
  if ! run_r4; then
    R4_RC=1
    issue "RW-R4 partial state recorded after nonzero wave result"
    commit_partial_r4 || true
    R4_COMMIT="$(git rev-parse HEAD)"
    write_status "R4" "partial" "commit=$R4_COMMIT"
  fi

  finalize_ledger || true
  log "repair-wave driver finish R1=$R1_RC R2=$R2_RC R3=$R3_RC R4=$R4_RC"
  if [[ "$R1_RC" -ne 0 || "$R2_RC" -ne 0 || "$R3_RC" -ne 0 || "$R4_RC" -ne 0 ]]; then
    exit 1
  fi
}

main "$@"
