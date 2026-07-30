#!/usr/bin/env bash
# D12 Step-0 — eval EXPANSION (NO retrain): per-building gssem Roofer Solids for gs_d4_dense, gs_b1_dense
# (existing ckpts, clipped) + raw_lidar(ALS) over a target list (default = 71 both-success survivors).
# Produces mob_eval/<arm>/roofer_*_orig + _orig_classified.las for the 3-axis defect metrics.
# Reuses the canonical tum_mob_baselines/tum_mob_tsdf_extract/tum_mob_eval harness. EPSG:25832. Observe only.
# Launch: setsid nohup bash scripts/evidence_and_attributes/p2_gsjso/run_d12_eval.sh [targets_file] > results/tum_transfer/mob/d12.log 2>&1 &
set -u
cd "$(dirname "$0")/../../.." || exit 1
OUT=results/tum_transfer/mob; WS=/workspace/JointBuildGS; U="$(id -u):$(id -g)"
TARGETS="$(cat "${1:-$OUT/d12_targets_71.txt}")"
GML="$WS/phases/p0-audit/data/raw/lod2/690_5334.gml $WS/phases/p0-audit/data/raw/lod2/690_5336.gml"
GEOJSON=results/tum_transfer/analysis/footprints_aoi.geojson
BASE=$OUT/baselines_d12.json
TOOLS="docker run --rm --user $U -v $PWD:/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0"
echo "[$(date '+%F %T')] D12 eval-expansion start; targets=$(echo $TARGETS | wc -w)"

# 1) baselines (bbox + ALS density per building) — required by tum_mob_eval
if [ ! -f "$BASE" ]; then
  $TOOLS python3 scripts/input_and_alignment/p2_gsjso/tum_mob_baselines.py --gml $GML \
    --geojson "$WS/$GEOJSON" --als-glob "$WS/phases/p0-audit/data/raw/als/*.laz" \
    --targets $TARGETS --out "$WS/$BASE" > "$OUT/d12_baselines.log" 2>&1
  echo "[$(date '+%F %T')] baselines rc=$? -> $BASE"
fi

# 2) extract gs_d4_dense + gs_b1_dense TSDF over the target boxes (clip of existing ckpt; NO retrain)
for arm in gs_d4_dense gs_b1_dense; do
  [ -f "$OUT/tsdf_d12_$arm.npz" ] && { echo "[$(date '+%F %T')] SKIP extract $arm"; continue; }
  [ -f "$OUT/$arm/ckpt/final.pt" ] || { echo "[$(date '+%F %T')] NO ckpt $arm"; continue; }
  docker compose run --rm -T dev python phases/p2-gsjso/scripts/tum_mob_tsdf_extract.py \
    --ckpt "$WS/$OUT/$arm/ckpt/final.pt" --out "$WS/$OUT/tsdf_d12_$arm.npz" \
    --min-obs 3 --voxel 0.05 --downscale 1.0 --targets $TARGETS > "$OUT/d12_extract_$arm.log" 2>&1
  echo "[$(date '+%F %T')] extract $arm rc=$?"
done

# 3a) eval GSSEM for the GS arms (gs_d4_dense, gs_b1_dense), ORIG density only. gssem read-out.
CFG_GS="gs_d4_dense=$OUT/tsdf_d12_gs_d4_dense.npz gs_b1_dense=$OUT/tsdf_d12_gs_b1_dense.npz"
python3 scripts/input_and_alignment/p2_gsjso/tum_mob_eval.py --configs $CFG_GS --geojson "$GEOJSON" \
  --baselines "$BASE" --targets $TARGETS --densities orig --classifier gssem \
  --out "$OUT/eval_d12_gssem.json" > "$OUT/d12_eval_gs.log" 2>&1
echo "[$(date '+%F %T')] eval GS(gssem) rc=$?"

# 3b) eval SMRF for raw_lidar (ALS has no GS semantics -> smrf ground + footprint overlay = ALS roof pts).
python3 scripts/input_and_alignment/p2_gsjso/tum_mob_eval.py --configs raw_lidar="$OUT/raw/raw_lidar.npz" --geojson "$GEOJSON" \
  --baselines "$BASE" --targets $TARGETS --densities orig --classifier smrf \
  --out "$OUT/eval_d12_raw.json" > "$OUT/d12_eval_raw.log" 2>&1
echo "[$(date '+%F %T')] eval raw_lidar(smrf) rc=$?  ===== D12 EVAL DONE ====="
