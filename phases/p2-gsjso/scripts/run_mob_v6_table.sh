#!/usr/bin/env bash
# P2 make-or-break v6 — Phase 4: RMS-to-reference (all 7 arms) + assemble the 8-way table.
# Run AFTER both arms finish (results/tum_transfer/mob/V6_PIPELINE_DONE && V6_RAW_DONE).
# Usage: bash phases/p2-gsjso/scripts/run_mob_v6_table.sh [matched|orig]
# Observation only; verdict = human. EPSG:25832. Docker-based.
set -u
cd "$(dirname "$0")/../../.." || exit 1
REPO="$(pwd)"; OUT=results/tum_transfer/mob
TAG="${1:-matched}"
TOOLS="jointbuildgs-p0-tools:t0"
ARMS="gs_seed_sparse gs_seed_dense gs_seed_acmp raw_sparse raw_dense raw_acmp raw_lidar"

[ -f "$OUT/V6_PIPELINE_DONE" ] || echo "[warn] GS arm not done (no V6_PIPELINE_DONE) — GS columns may be partial"
[ -f "$OUT/V6_RAW_DONE" ]      || echo "[warn] raw arm not done (no V6_RAW_DONE) — raw columns may be partial"

echo "[$(date '+%F %T')] ref-RMS (all 7 arms) -> ref_rms_v6.csv"
# shellcheck disable=SC2086
docker run --rm --user "$(id -u):$(id -g)" -v "$REPO":/workspace/JointBuildGS -w /workspace/JointBuildGS "$TOOLS" \
  python3 phases/p2-gsjso/scripts/tum_mob_ref_rms.py --arms $ARMS \
    --out /workspace/JointBuildGS/results/tum_transfer/mob_analysis/ref_rms_v6.csv \
  > "$OUT/refrms_v6.log" 2>&1
echo "[$(date '+%F %T')] ref-RMS rc=$?  ($(tail -1 "$OUT/refrms_v6.log"))"

echo "[$(date '+%F %T')] assemble 8-way table (tag=$TAG)"
python3 phases/p2-gsjso/scripts/tum_mob_v6_table.py --tag "$TAG"
echo "[$(date '+%F %T')] ===== Phase 4 table done -> $OUT/REPORT_v6.md ====="
