#!/usr/bin/env bash
# P2-D6 step0 — curved-roof over-seg CLEAN re-diagnosis (gssem canonical; smrf 병기). Observation only.
# 1) regenerate smrf-classified GS roof points (병기, temp; canonical gssem disk untouched)
# 2) component (a)+(b): d6_overseg_diag.py   [p0-tools]
# 3) component (c): d6_roofer_sweep.py        [host -> P0 compose roofer]
# EPSG:25832 · Docker · idempotent (skip steps whose outputs exist). Verdict = 김휘영.
set -euo pipefail
cd "$(dirname "$0")/../../.."   # repo root
REPO=$(pwd)
TOOLS="docker run --rm -i --user $(id -u):$(id -g) -v $REPO:/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0"
GEOJSON=/workspace/JointBuildGS/results/tum_transfer/analysis/footprints_aoi.geojson
SMRF_TMP=phases/p0-audit/runs/_d6_smrf_tmp
PACK=results/tum_transfer/mob/analysis_pack_d6
mkdir -p "$PACK" "$SMRF_TMP"

# ---- versions / provenance ----
{
  echo "# D6 step0 run provenance — $(date '+%F %T')"
  echo "git_commit: $(git rev-parse HEAD)  branch: $(git rev-parse --abbrev-ref HEAD)"
  echo "roofer_image: $(docker inspect --format '{{index .RepoDigests 0}}' 3dgi/roofer:v1.0.0 2>/dev/null || echo 3dgi/roofer:v1.0.0)"
  echo "p0tools_image: $(docker inspect --format '{{.Id}}' jointbuildgs-p0-tools:t0 2>/dev/null)"
  echo "targets: 4906969(curved) 42364659(composite) 4906972(flat)"
  echo "GS arms: gs_d4_dense gs_d4_acmp (cp-fair D4, gssem canonical disk)  LiDAR: raw_lidar"
} > "$PACK/versions_d6.txt"
cat "$PACK/versions_d6.txt"

# ---- 1) smrf 병기: regenerate GS roof points via SMRF (deterministic; canonical disk untouched) ----
echo "[1] smrf re-classify GS (병기) -> $SMRF_TMP"
for arm in gs_d4_dense gs_d4_acmp; do
  for t in 4906969 42364659 4906972; do
    bid="DEBY_LOD2_$t"
    if [ -f "$SMRF_TMP/$arm/${bid}_orig_classified.las" ]; then
      echo "  skip $arm/$t (exists)"; continue
    fi
    mkdir -p "$SMRF_TMP/$arm"
    echo "  smrf $arm/$t"
    $TOOLS python3 scripts/input_and_alignment/p2_gsjso/_mob_prep_las.py \
      --tsdf "/workspace/JointBuildGS/results/tum_transfer/mob/tsdf_${arm}.npz" \
      --bid "$bid" --geojson "$GEOJSON" --target-density 0 \
      --outdir "/workspace/JointBuildGS/$SMRF_TMP/$arm" --tag orig \
      > "$SMRF_TMP/$arm/${bid}_prep.log" 2>&1 || echo "    [warn] smrf prep failed $arm/$t (see log)"
  done
done

# ---- 2) component (a)+(b): roughness + density ----
echo "[2] d6_overseg_diag.py (roughness + density)"
$TOOLS python3 scripts/evidence_and_attributes/p2_gsjso/d6_overseg_diag.py

# ---- 3) component (c): Roofer epsilon / min-points sweep ----
echo "[3] d6_roofer_sweep.py (Roofer threshold sweep)"
python3 scripts/evidence_and_attributes/p2_gsjso/d6_roofer_sweep.py

# ---- 4) supplementary (b)x(c): density-match -> Roofer (separate density vs threshold) ----
echo "[4] d6_density_match.py (GS -> LiDAR density LAS)  [p0-tools]"
$TOOLS python3 scripts/evidence_and_attributes/p2_gsjso/d6_density_match.py
echo "[4b] d6_densmatch_roofer.py (Roofer on density-matched clouds)  [host]"
python3 scripts/evidence_and_attributes/p2_gsjso/d6_densmatch_roofer.py

# ---- 5) figures (clean; supersedes any in-diag scatter) ----
echo "[5] d6_figs.py (profile + roughness-dist + facets-vs-epsilon)  [p0-tools]"
$TOOLS python3 scripts/evidence_and_attributes/p2_gsjso/d6_figs.py

echo "[done] D6 step0 -> $PACK/{overseg_diag_d6,roofer_sweep_d6,density_match_d6,densmatch_roofer_d6}.csv + docs/figs/W_D6/"
