#!/usr/bin/env bash
# P2 make-or-break — sequential 5-way ablation training on GPU1 (dev container, NVIDIA_VISIBLE_DEVICES=1).
# vanilla -> baseline(+sem) -> mutual -> structure -> both. Same validated base (configs/input_and_alignment/tum_mob/*.yaml,
# w_distort=0 fallback). Each run writes its own log + a .done flag (rc); ALL.done at the end.
# Engine logic unchanged — config + clean labels only. Reproducible: re-run this script.
set -u
cd "$(dirname "$0")/../../.." || exit 1     # repo root
OUT=results/tum_transfer/mob
mkdir -p "$OUT"
echo "[$(date '+%F %T')] mob ablation chain start (GPU1, sequential)"
for name in vanilla baseline mutual structure both; do
  echo "[$(date '+%F %T')] START $name"
  docker compose run --rm -T dev python -m src.stage2.train \
      --config /workspace/JointBuildGS/configs/input_and_alignment/tum_mob/$name.yaml \
      > "$OUT/train_$name.log" 2>&1
  rc=$?
  echo "[$(date '+%F %T')] END $name rc=$rc"
  echo "$rc" > "$OUT/$name.done"
done
touch "$OUT/ALL.done"
echo "[$(date '+%F %T')] ALL DONE"
