#!/usr/bin/env bash
# P2 make-or-break — FULL detached pipeline: train 5 ablations -> extract per-config TSDF -> 5-way eval.
# Designed to survive the interactive session closing (launch with: setsid nohup bash run_mob_all.sh ... &).
# Idempotent/resumable: skips any stage whose output already exists. Per-stage logs + .done flags.
# GPU1 (dev) for train+extract; CPU (P0 tools/roofer/val3dity) for eval. Engine unchanged.
set -u
cd "$(dirname "$0")/../../.." || exit 1
OUT=results/tum_transfer/mob
WS=/workspace/JointBuildGS
mkdir -p "$OUT"
echo "[$(date '+%F %T')] ===== MOB full pipeline start ====="

# 1) TRAIN (skip if final.pt already present)
for name in vanilla baseline mutual structure both; do
  if [ -f "$OUT/$name/ckpt/final.pt" ]; then echo "[$(date '+%F %T')] SKIP train $name"; continue; fi
  echo "[$(date '+%F %T')] TRAIN $name"
  docker compose run --rm -T dev python -m src.stage2.train \
      --config "$WS/configs/input_and_alignment/tum_mob/$name.yaml" > "$OUT/train_$name.log" 2>&1
  echo "$?" > "$OUT/$name.train.done"
  echo "[$(date '+%F %T')] TRAIN $name rc=$(cat "$OUT/$name.train.done")"
done
echo "[$(date '+%F %T')] ===== training done ====="

# 2) EXTRACT per-config TSDF over the 11 make-or-break buildings (min-obs 3)
for name in vanilla baseline mutual structure both; do
  if [ -f "$OUT/tsdf_$name.npz" ]; then echo "[$(date '+%F %T')] SKIP extract $name"; continue; fi
  if [ ! -f "$OUT/$name/ckpt/final.pt" ]; then echo "[$(date '+%F %T')] NO ckpt for $name, skip extract"; continue; fi
  echo "[$(date '+%F %T')] EXTRACT $name"
  docker compose run --rm -T dev python scripts/stage3_readout/tum_mob_tsdf_extract.py \
      --ckpt "$WS/$OUT/$name/ckpt/final.pt" --out "$WS/$OUT/tsdf_$name.npz" \
      --min-obs 3 --voxel 0.05 --downscale 1.0 > "$OUT/extract_$name.log" 2>&1
  echo "$?" > "$OUT/$name.extract.done"
  echo "[$(date '+%F %T')] EXTRACT $name rc=$(cat "$OUT/$name.extract.done")"
done
echo "[$(date '+%F %T')] ===== extraction done ====="

# 3) EVAL (density-corrected 5-way; orig + ALS-density-matched) — runs on host, drives Docker
echo "[$(date '+%F %T')] EVAL"
python3 scripts/input_and_alignment/tum_transfer/tum_mob_eval.py \
  --configs vanilla="$OUT/tsdf_vanilla.npz" baseline="$OUT/tsdf_baseline.npz" \
            mutual="$OUT/tsdf_mutual.npz" structure="$OUT/tsdf_structure.npz" both="$OUT/tsdf_both.npz" \
  --out "$OUT/eval_results.json" > "$OUT/eval.log" 2>&1
echo "$?" > "$OUT/eval.done"
touch "$OUT/PIPELINE_ALL_DONE"
echo "[$(date '+%F %T')] ===== ALL DONE (eval rc=$(cat "$OUT/eval.done")) ====="
