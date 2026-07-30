#!/usr/bin/env bash
# P2 make-or-break v6 — GS arm FULL detached pipeline for the MVS-seed configs:
#   train gs_seed_{sparse,dense,acmp} -> extract per-config TSDF -> 3-way eval (Roofer/val3dity/facet/RMS).
# Mirrors run_mob_all.sh exactly (same dev/tools/roofer images, same TSDF + tum_mob_eval harness).
# Idempotent/resumable: skips any stage whose output exists. Per-stage logs + .done flags + versions.txt.
# Launch detached:  setsid nohup bash scripts/input_and_alignment/p2_gsjso/run_mob_v6.sh > results/tum_transfer/mob/v6.log 2>&1 &
# Engine logic unchanged. EPSG:25832. Observation only.
set -u
cd "$(dirname "$0")/../../.." || exit 1
OUT=results/tum_transfer/mob
WS=/workspace/JointBuildGS
CONFIGS="gs_seed_sparse gs_seed_dense gs_seed_acmp"
mkdir -p "$OUT"
echo "[$(date '+%F %T')] ===== MOB v6 (MVS-seed) pipeline start ====="

# 0) versions.txt per config (commit / params / datum / seed cloud paths+counts / images)
COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "UNKNOWN")
for name in $CONFIGS; do
  od="$OUT/$name"; mkdir -p "$od"
  {
    echo "run=$name  stamped=$(date '+%F %T')"
    echo "git_commit=$COMMIT"
    echo "datum: GS-LOCAL = EPSG:25832 - [690953,5336071,604] (ellipsoidal); dim shift -604, acmp shift -556 (geoid -48)"
    echo "config=configs/tum_mob/$name.yaml"
    case "$name" in
      gs_seed_sparse) echo "init=COLMAP sparse points3D (default, ~372k)";;
      gs_seed_dense)  echo "init=seed_dense.ply (DIM, AOI, voxel0.40, concat onto SfM)  $(stat -c%s results/tum_transfer/mob_analysis/seed/seed_dense.ply 2>/dev/null)B";;
      gs_seed_acmp)   echo "init=seed_acmp.ply (ACMP, AOI, voxel0.40, concat onto SfM)  $(stat -c%s results/tum_transfer/mob_analysis/seed/seed_acmp.ply 2>/dev/null)B";;
    esac
    echo "images: dev=$(docker images --no-trunc -q jointbuildgs:dev 2>/dev/null)  tools=$(docker images --no-trunc -q jointbuildgs-p0-tools:t0 2>/dev/null)"
    echo "roofer=3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2"
    grep -E '^(sem_detach_geometry|w_sem|w_structure|w_mutual|w_nc|w_depth|w_normal|max_iter|refine_every|grow_grad2d|init_pointcloud|init_pointcloud_mode):' "configs/tum_mob/$name.yaml"
  } > "$od/versions.txt"
done
echo "[$(date '+%F %T')] versions.txt written (commit=$COMMIT)"

# 1) TRAIN (skip if final.pt present)
for name in $CONFIGS; do
  if [ -f "$OUT/$name/ckpt/final.pt" ]; then echo "[$(date '+%F %T')] SKIP train $name"; continue; fi
  echo "[$(date '+%F %T')] TRAIN $name"
  docker compose run --rm -T dev python -m src.stage2.train \
      --config "$WS/configs/tum_mob/$name.yaml" > "$OUT/train_$name.log" 2>&1
  echo "$?" > "$OUT/$name.train.done"
  echo "[$(date '+%F %T')] TRAIN $name rc=$(cat "$OUT/$name.train.done")"
done
echo "[$(date '+%F %T')] ===== training done ====="

# 2) EXTRACT per-config TSDF over the 11 make-or-break buildings (min-obs 3)
for name in $CONFIGS; do
  if [ -f "$OUT/tsdf_$name.npz" ]; then echo "[$(date '+%F %T')] SKIP extract $name"; continue; fi
  if [ ! -f "$OUT/$name/ckpt/final.pt" ]; then echo "[$(date '+%F %T')] NO ckpt for $name, skip extract"; continue; fi
  echo "[$(date '+%F %T')] EXTRACT $name"
  docker compose run --rm -T dev python phases/p2-gsjso/scripts/tum_mob_tsdf_extract.py \
      --ckpt "$WS/$OUT/$name/ckpt/final.pt" --out "$WS/$OUT/tsdf_$name.npz" \
      --min-obs 3 --voxel 0.05 --downscale 1.0 > "$OUT/extract_$name.log" 2>&1
  echo "$?" > "$OUT/$name.extract.done"
  echo "[$(date '+%F %T')] EXTRACT $name rc=$(cat "$OUT/$name.extract.done")"
done
echo "[$(date '+%F %T')] ===== extraction done ====="

# 2b) baselines.json (ref facet counts + ALS density) — prereq for eval; build if missing
if [ ! -f "$OUT/baselines.json" ]; then
  echo "[$(date '+%F %T')] baselines.json missing -> compute"
  python3 scripts/input_and_alignment/p2_gsjso/tum_mob_baselines.py > "$OUT/baselines.log" 2>&1 || \
    echo "[$(date '+%F %T')] WARN baselines.py failed (see baselines.log)"
fi

# 3) EVAL (density-corrected 3-way; orig + ALS-density-matched) — host drives Docker
echo "[$(date '+%F %T')] EVAL"
python3 scripts/input_and_alignment/p2_gsjso/tum_mob_eval.py \
  --configs gs_seed_sparse="$OUT/tsdf_gs_seed_sparse.npz" \
            gs_seed_dense="$OUT/tsdf_gs_seed_dense.npz" \
            gs_seed_acmp="$OUT/tsdf_gs_seed_acmp.npz" \
  --out "$OUT/eval_v6.json" > "$OUT/eval_v6.log" 2>&1
echo "$?" > "$OUT/eval_v6.done"
touch "$OUT/V6_PIPELINE_DONE"
echo "[$(date '+%F %T')] ===== V6 ALL DONE (eval rc=$(cat "$OUT/eval_v6.done")) ====="
