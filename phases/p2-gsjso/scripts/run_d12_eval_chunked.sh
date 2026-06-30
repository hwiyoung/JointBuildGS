#!/usr/bin/env bash
# D12 Step-0 (CHUNKED) — the 71-box single extract OOM-kills (rc137, surf_backproj 318M pts). So extract+eval
# in CHUNKS of CHUNK buildings (each extract stays in memory, like the working pilot); the per-building Roofer
# Solids ACCUMULATE in mob_eval across chunks. gssem for GS arms; raw_lidar(ALS) already done by run_d12_eval.sh.
# Idempotent (skips a chunk whose buildings all have classified.las). NO retrain. EPSG:25832. Observe only.
# Launch: setsid nohup bash phases/p2-gsjso/scripts/run_d12_eval_chunked.sh > results/tum_transfer/mob/d12_chunk.log 2>&1 &
set -u
cd "$(dirname "$0")/../../.." || exit 1
OUT=results/tum_transfer/mob; WS=/workspace/JointBuildGS
GEOJSON=results/tum_transfer/analysis/footprints_aoi.geojson
BASE=$OUT/baselines_d12.json
CHUNK=10
ALL="$(cat $OUT/d12_targets_71.txt)"
read -ra A <<< "$ALL"; N=${#A[@]}
echo "[$(date '+%F %T')] D12 chunked: $N targets, chunk=$CHUNK"
ci=0
for ((i=0; i<N; i+=CHUNK)); do
  ci=$((ci+1)); CH="${A[@]:i:CHUNK}"
  echo "[$(date '+%F %T')] === chunk $ci : $CH ==="
  rm -f "$OUT/tsdf_d12_gs_d4_dense.npz" "$OUT/tsdf_d12_gs_b1_dense.npz"
  for arm in gs_d4_dense gs_b1_dense; do
    docker compose run --rm -T dev python phases/p2-gsjso/scripts/tum_mob_tsdf_extract.py \
      --ckpt "$WS/$OUT/$arm/ckpt/final.pt" --out "$WS/$OUT/tsdf_d12_$arm.npz" \
      --min-obs 3 --voxel 0.05 --downscale 1.0 --targets $CH > "$OUT/d12c_extract_${ci}_$arm.log" 2>&1
    rc=$?; [ $rc -eq 0 ] && [ -f "$OUT/tsdf_d12_$arm.npz" ] || echo "[$(date '+%F %T')] WARN chunk $ci $arm rc=$rc (npz=$([ -f "$OUT/tsdf_d12_$arm.npz" ] && echo ok || echo MISSING))"
  done
  CFG="gs_d4_dense=$OUT/tsdf_d12_gs_d4_dense.npz gs_b1_dense=$OUT/tsdf_d12_gs_b1_dense.npz"
  python3 phases/p2-gsjso/scripts/tum_mob_eval.py --configs $CFG --geojson "$GEOJSON" \
    --baselines "$BASE" --targets $CH --densities orig --classifier gssem \
    --out "$OUT/eval_d12c_${ci}.json" > "$OUT/d12c_eval_${ci}.log" 2>&1
  echo "[$(date '+%F %T')] chunk $ci eval rc=$?"
done
echo "[$(date '+%F %T')] ===== D12 CHUNKED DONE ====="
