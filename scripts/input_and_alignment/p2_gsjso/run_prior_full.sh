#!/usr/bin/env bash
# P2-D 전체 prior 수트 — 2-arm pipeline: PARALLEL 2-GPU train -> semantic TSDF -> eval (gssem + smrf).
# Turns ON all three levers vs v6 (gs_seed_*_protect): depth/normal supervision (Lever 1),
# surface-level G2 structure (Lever 2), GS-semantic classification read-out (Lever 3).
# MUST-EQ otherwise identical to v6. Engine change isolated on branch feature/p2-prior-full.
# PREREQ: depth/normal maps staged at data_geoidfix/stereo (scripts/input_and_alignment/p2_gsjso/prior_full_stereo.sh).
# Launch: setsid nohup bash scripts/input_and_alignment/p2_gsjso/run_prior_full.sh > results/tum_transfer/mob/prior_full.log 2>&1 &
# dev service = host GPU1; 2nd arm overridden to host GPU0. EPSG:25832.
set -u
cd "$(dirname "$0")/../../.." || exit 1
OUT=results/tum_transfer/mob; WS=/workspace/JointBuildGS
mkdir -p "$OUT"
COMMIT=$(git rev-parse HEAD); BR=$(git rev-parse --abbrev-ref HEAD)
ARMS="gs_prior_full_dense gs_prior_full_acmp"
GEOJSON=results/tum_transfer/analysis/footprints_aoi.geojson

# guard: maps must be staged or training's silent-zero guard will (correctly) abort
if [ ! -e "$OUT/../data_geoidfix/stereo" ]; then
  echo "FATAL: results/tum_transfer/data_geoidfix/stereo missing — run prior_full_stereo.sh first"; exit 2
fi

for name in $ARMS; do
  od="$OUT/$name"; mkdir -p "$od"
  {
    echo "run=$name  stamped=$(date '+%F %T')  git=$COMMIT  branch=$BR"
    echo "datum: GS-LOCAL=EPSG:25832-[690953,5336071,604]; acmp seed -556 (geoid)"
    echo "levers: L1 depth/normal(warmup->ramp, MVS maps@data_geoidfix/stereo) + L2 structure_grouping=g2 + L3 gssem read-out"
    echo "dev image=$(docker images --no-trunc -q jointbuildgs:dev)"
    grep -E '^(seed_protect|init_pointcloud|sem_detach_geometry|w_sem|w_nc|w_depth|w_normal|depth_schedule|depth_warmup|w_structure|structure_grouping|structure_min_group|max_iter|grow_grad2d|refine_stop_iter):' "configs/tum_mob/$name.yaml"
  } > "$od/versions.txt"
done
echo "[$(date '+%F %T')] ===== D prior-full start (commit=$COMMIT branch=$BR) ====="

train_one(){  # $1=config name  $2=host GPU
  if [ -f "$OUT/$1/ckpt/final.pt" ]; then echo "[$(date '+%F %T')] SKIP train $1"; return; fi
  echo "[$(date '+%F %T')] TRAIN $1 on host-GPU$2"
  docker compose run --rm -T -e NVIDIA_VISIBLE_DEVICES=$2 dev python -m src.stage2.train \
      --config "$WS/configs/tum_mob/$1.yaml" > "$OUT/train_$1.log" 2>&1
  echo "$?" > "$OUT/$1.train.done"
}

# 1) PARALLEL train on 2 GPUs
train_one gs_prior_full_dense 1 & P0=$!
train_one gs_prior_full_acmp  0 & P1=$!
wait $P0 $P1
echo "[$(date '+%F %T')] ===== training done (dense rc=$(cat "$OUT/gs_prior_full_dense.train.done" 2>/dev/null) acmp rc=$(cat "$OUT/gs_prior_full_acmp.train.done" 2>/dev/null)) ====="

# 2) EXTRACT semantic TSDF (sequential, default GPU1) — carries P_class for the gssem read-out
for name in $ARMS; do
  [ -f "$OUT/tsdf_$name.npz" ] && { echo "[$(date '+%F %T')] SKIP extract $name"; continue; }
  [ -f "$OUT/$name/ckpt/final.pt" ] || { echo "[$(date '+%F %T')] NO ckpt $name"; continue; }
  echo "[$(date '+%F %T')] EXTRACT $name (semantic)"
  docker compose run --rm -T dev python phases/p2-gsjso/scripts/tum_mob_tsdf_extract.py \
      --ckpt "$WS/$OUT/$name/ckpt/final.pt" --out "$WS/$OUT/tsdf_$name.npz" \
      --min-obs 3 --voxel 0.05 --downscale 1.0 > "$OUT/extract_$name.log" 2>&1
  echo "$?" > "$OUT/$name.extract.done"
done

# 3) EVAL — gssem (D Lever-3 read-out) AND smrf (isolate training-prior effect vs v6), matched+orig
CFG="gs_prior_full_dense=$OUT/tsdf_gs_prior_full_dense.npz gs_prior_full_acmp=$OUT/tsdf_gs_prior_full_acmp.npz"
echo "[$(date '+%F %T')] EVAL gssem (GS-semantic read-out)"
python3 scripts/input_and_alignment/p2_gsjso/tum_mob_eval.py --configs $CFG --geojson "$GEOJSON" \
  --classifier gssem --out "$OUT/eval_prior_full_gssem.json" > "$OUT/eval_prior_full_gssem.log" 2>&1
echo "[$(date '+%F %T')] EVAL smrf (control read-out, vs v6)"
python3 scripts/input_and_alignment/p2_gsjso/tum_mob_eval.py --configs $CFG --geojson "$GEOJSON" \
  --classifier smrf --out "$OUT/eval_prior_full_smrf.json" > "$OUT/eval_prior_full_smrf.log" 2>&1
echo "[$(date '+%F %T')] ===== D prior-full DONE ====="
