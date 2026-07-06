#!/usr/bin/env bash
# P2 make-or-break v6 / E5 — prepare seed init clouds (sparse=COLMAP, dense=DIM, acmp=ACMP).
# dense/acmp PDAL pipelines: AOI crop (UTM) -> per-cloud geoid Z shift to GS-LOCAL ellipsoidal
# (dim -604, acmp -558.3) -> outlier z-clip [-65,30] local -> voxel downsample (<=~3M) ->
# write GS-LOCAL .ply. sparse uses native COLMAP points3D, AOI crop, and the same local z band.
# The training image then reads the .ply via src/stage2/pointcloud_io. EPSG:25832. Docker-based.
# Usage: bash tum_mob_seed_prep.sh         (runs sparse+dense+acmp)
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
TOOLS="jointbuildgs-p0-tools:t0"
OUT="$REPO/results/tum_transfer/mob_analysis/seed"
mkdir -p "$OUT"

run_one () {
  local name="$1" json="$2"
  echo "[seed-prep:$name] $(date '+%F %T') pipeline=$json"
  docker run --rm --user "$(id -u):$(id -g)" -v "$REPO":/workspace/JointBuildGS -w /workspace/JointBuildGS "$TOOLS" \
    pdal pipeline "/workspace/JointBuildGS/phases/p2-gsjso/scripts/$json"
  local ply="$OUT/seed_$name.ply"
  local n
  n=$(docker run --rm -v "$REPO":/ws "$TOOLS" pdal info --summary "/ws/results/tum_transfer/mob_analysis/seed/seed_$name.ply" 2>/dev/null \
      | grep -oE '"num_points"[: ]+[0-9]+' | grep -oE '[0-9]+')
  echo "[seed-prep:$name] DONE -> seed_$name.ply  N=$n"
}

echo "[seed-prep:sparse] $(date '+%F %T')"
docker run --rm --user "$(id -u):$(id -g)" -v "$REPO":/workspace/JointBuildGS -w /workspace/JointBuildGS "$TOOLS" \
  python3 phases/p2-gsjso/scripts/seed_prep_sparse.py
run_one dense seed_prep_dense.json
run_one acmp  seed_prep_acmp.json
echo "[seed-prep] all done $(date '+%F %T')"
