#!/usr/bin/env bash
# S3-A-prime Phase-0 §3-3: cached/selected FM P0 fill + existing DIM support.
# Processing runs in the pinned P0 tools and Roofer containers. No GS training
# or MASt3R inference. Roofer receives only a point-evidence-derived roofprint.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
IMAGE="jointbuildgs-p0-tools:t0"
ROOFER="3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
RUN_REL="phases/p2-gsjso/runs/e5_c001/20260715_e5_c001_s3ap_phase0_baselines"
ROOFER_OUT="$REPO/$RUN_REL/roofer"
ROOFER_LOG="$REPO/$RUN_REL/roofer.log"
ARGS=("$@")

docker run --rm -i \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e XDG_CACHE_HOME=/tmp \
  -v "$REPO:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "$IMAGE" \
  python3 phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase0_baselines.py "${ARGS[@]}"

rm -rf "$ROOFER_OUT"
mkdir -p "$ROOFER_OUT"
ROOFER_EXIT=0
if docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$REPO:/workspace/JointBuildGS" \
  -w "/workspace/JointBuildGS/$RUN_REL" \
  "$ROOFER" \
  --id-attribute building_id --jobs 3 --srs EPSG:25832 \
  --bld-class 6 --grnd-class 2 --lod22 \
  "/workspace/JointBuildGS/$RUN_REL/p0_fill_classified.las" \
  "/workspace/JointBuildGS/$RUN_REL/point_evidence_derived_roofprints.geojson" \
  "/workspace/JointBuildGS/$RUN_REL/roofer" \
  >"$ROOFER_LOG" 2>&1
then
  ROOFER_EXIT=0
else
  ROOFER_EXIT=$?
fi

docker run --rm -i \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib -e XDG_CACHE_HOME=/tmp \
  -v "$REPO:/workspace/JointBuildGS" \
  -w /workspace/JointBuildGS \
  "$IMAGE" \
  python3 phases/p2-gsjso/scripts/e5_c001/e5_c001_s3ap_phase0_roofer_finalize.py \
    --roofer-exit-code "$ROOFER_EXIT"
