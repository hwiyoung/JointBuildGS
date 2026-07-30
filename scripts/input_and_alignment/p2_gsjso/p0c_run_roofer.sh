#!/usr/bin/env bash
# P0 completeness re-verification (Step 2) — run Roofer on a cloud x param-cell, then eval.
# Reuses canonical roofer image + AOI box + footprint GPKG + the EXACT P0 parse chain.
# Usage: p0c_run_roofer.sh <cloud_laz> <label> "<extra_roofer_flags>"
# Observation only. EPSG:25832. Docker-based.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
CLOUD="$1"; LABEL="$2"; EXTRA="${3:-}"
ROOFER="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
TOOLS="jointbuildgs-p0-tools:t0"
GPKG="$REPO/phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg"
BOX="690791.740 5335864.050 691154.650 5336353.850"
OUTBASE="$REPO/results/tum_transfer/mob_analysis/p0c_step2"
JSONL_DIR="$OUTBASE/roofer_$LABEL"
EVAL_DIR="$OUTBASE/eval"
rm -rf "$JSONL_DIR"; mkdir -p "$JSONL_DIR" "$EVAL_DIR"

echo "[roofer:$LABEL] cloud=$(basename "$CLOUD") flags='$EXTRA'"
t0=$(date +%s)
# shellcheck disable=SC2086
docker run --rm --user "$(id -u):$(id -g)" -v "$REPO":/workspace/JointBuildGS -w /workspace/JointBuildGS "$ROOFER" \
  --id-attribute building_id --jobs 32 --srs EPSG:25832 \
  --box 690791.740 5335864.050 691154.650 5336353.850 $EXTRA \
  "/workspace/JointBuildGS/${CLOUD#"$REPO/"}" \
  "/workspace/JointBuildGS/phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg" \
  "/workspace/JointBuildGS/results/tum_transfer/mob_analysis/p0c_step2/roofer_$LABEL" \
  > "$JSONL_DIR/roofer.log" 2>&1 || { echo "[roofer FAILED, tail log]"; tail -15 "$JSONL_DIR/roofer.log"; exit 1; }
echo "[roofer:$LABEL done $(( $(date +%s)-t0 ))s] jsonl=$(ls "$JSONL_DIR"/*.city.jsonl 2>/dev/null | wc -l)"

docker run --rm --user "$(id -u):$(id -g)" -v "$REPO":/workspace/JointBuildGS -w /workspace/JointBuildGS "$TOOLS" \
  python3 /workspace/JointBuildGS/scripts/input_and_alignment/p2_gsjso/p0c_roofer_eval.py \
    --jsonl-dir "/workspace/JointBuildGS/results/tum_transfer/mob_analysis/p0c_step2/roofer_$LABEL" \
    --label "$LABEL" \
    --outdir "/workspace/JointBuildGS/results/tum_transfer/mob_analysis/p0c_step2/eval"
