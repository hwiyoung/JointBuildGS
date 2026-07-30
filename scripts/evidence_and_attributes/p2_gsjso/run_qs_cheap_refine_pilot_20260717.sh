#!/usr/bin/env bash
# D-wave: canonical dense(w2_1) -> MLS-style default refinement -> canonical Roofer -> A-path score.
set -Eeuo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO"

RUN_REL="phases/p2-gsjso/runs/quality_score/20260717_qs_cheap_refine_pilot"
RUN="$REPO/$RUN_REL"
STATUS="$RUN/status.json"
ISSUES="$REPO/phases/p2-gsjso/docs/issues.md"
TOOLS_IMAGE="jointbuildgs-p0-tools:t0"
ROOFER_IMAGE="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
UID_GID="$(id -u):$(id -g)"

mkdir -p "$RUN/logs" "$RUN/roofer"

run_tools() {
  docker run --rm -i --user "$UID_GID" \
    -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e XDG_CACHE_HOME=/tmp \
    -v "$REPO:/workspace/JointBuildGS" \
    -w /workspace/JointBuildGS \
    "$TOOLS_IMAGE" "$@"
}

write_status() {
  local state="$1"
  local detail="$2"
  run_tools python3 - "$state" "$detail" <<'PY' > "$STATUS.tmp"
import json
import sys
from datetime import datetime, timezone
print(json.dumps({
    "updated_utc": datetime.now(timezone.utc).isoformat(),
    "task": "OVN-D",
    "state": sys.argv[1],
    "detail": sys.argv[2],
    "learning_runs_started": 0,
    "new_inference_runs": 0,
}, ensure_ascii=False, indent=2))
PY
  mv "$STATUS.tmp" "$STATUS"
}

on_error() {
  local code=$?
  trap - ERR
  write_status "failed" "driver exited at line ${BASH_LINENO[0]} code=$code"
  printf -- "- %s OVN-D execution failed: line=%s exit_code=%s; learning_runs_started=0\n" \
    "$(date '+%Y-%m-%d %H:%M:%S')" "${BASH_LINENO[0]}" "$code" >> "$ISSUES"
  exit "$code"
}
trap on_error ERR

write_status "running" "prepare"

run_tools python3 scripts/quality_score/p2_gsjso/qs_cheap_refine_pilot.py prepare \
  > "$RUN/logs/prepare.log" 2>&1

write_status "running" "MLS default refinement"
run_tools python3 scripts/evidence_and_attributes/p2_gsjso/overseg_smooth.py \
  --in "/workspace/JointBuildGS/$RUN_REL/input/dense_w2_1_c001_classified.laz" \
  --out "/workspace/JointBuildGS/$RUN_REL/input/dense_w2_1_c001_mls_default.laz" \
  > "$RUN/logs/refine.log" 2>&1

BBOX=($(run_tools python3 - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("phases/p2-gsjso/runs/quality_score/20260717_qs_cheap_refine_pilot/prepared.json").read_text())
print(" ".join(str(value) for value in data["clip_bbox_epsg25832"]))
PY
))

write_status "running" "canonical Roofer default assembly"
docker run --rm --user "$UID_GID" \
  -v "$REPO:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "$ROOFER_IMAGE" \
  --id-attribute building_id \
  --box "${BBOX[@]}" \
  "/workspace/JointBuildGS/$RUN_REL/input/dense_w2_1_c001_mls_default.laz" \
  "/workspace/JointBuildGS/$RUN_REL/input/footprints_c001.gpkg" \
  "/workspace/JointBuildGS/$RUN_REL/roofer" \
  > "$RUN/logs/roofer.log" 2>&1

write_status "running" "val3dity and A-path scoring"
run_tools python3 scripts/quality_score/p2_gsjso/qs_cheap_refine_pilot.py finalize \
  > "$RUN/logs/finalize.log" 2>&1

run_tools python3 - <<'PY'
import csv
import json
from pathlib import Path

rows = list(csv.DictReader(Path("docs/experiments/pilots/qs_cheap_refine_pilot/tables/qs_cheap_refine_pilot.csv").open()))
manifest = json.loads(Path("phases/p2-gsjso/runs/quality_score/20260717_qs_cheap_refine_pilot/manifest.json").read_text())
if len(rows) != 18 or manifest["population_count"] != 18:
    raise SystemExit(f"D cardinality drift rows={len(rows)} manifest={manifest['population_count']}")
if any(row["learning_runs_started"] != "0" or row["new_inference_runs"] != "0" for row in rows):
    raise SystemExit("D learning/inference flag drift")
if not Path("docs/figs/qs_cheap_refine_pilot.png").is_file():
    raise SystemExit("D figure missing")
print(json.dumps({"rows": len(rows), "summary": manifest["summary"], "learning_runs_started": 0}))
PY

write_status "complete" "18 rows, figure, manifest, learning_runs_started=0"
