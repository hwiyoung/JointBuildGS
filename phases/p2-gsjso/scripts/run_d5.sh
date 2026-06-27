#!/usr/bin/env bash
# P2-D5 — cp ablation (de-noise FIXED = D4, only cp varies). 6-arm pipeline mirroring run_d4.sh:
#   3 SEQUENTIAL 2-GPU pairs (dense host-GPU1 | acmp host-GPU0): D5a (cp off) -> D5b (cp hard) -> D5c (cp early)
#   -> semantic TSDF -> eval (gssem + smrf), matched+orig. ~4h/arm, ~13h total wall on 2 GPUs.
# D5 = config-only loss-balance change vs D4 (engine UNCHANGED). MUST-EQ otherwise identical to D4.
#   D5a w_structure_cp 0.0 (warmup 15000) | D5b w_structure_cp 0.03 (warmup 15000) | D5c w_structure_cp 0.01 (warmup 5000)
#   (cp FAIR 0.01/warmup 15000 = D4 itself, REUSED — not retrained here.)
# Spec/pre-registration: P2_D5_cp_ablation_사양_사전등록_20260626.md. EPSG:25832. branch feature/p2-prior-full.
# PREREQ: depth/normal maps staged at data_geoidfix/stereo (prior_full_stereo.sh) — same as D/D4.
# Idempotent: skips train/extract whose outputs already exist (safe to re-run / resume).
# Launch: setsid nohup bash phases/p2-gsjso/scripts/run_d5.sh > results/tum_transfer/mob/d5.log 2>&1 &
set -u
cd "$(dirname "$0")/../../.." || exit 1
OUT=results/tum_transfer/mob; WS=/workspace/JointBuildGS
mkdir -p "$OUT"
COMMIT=$(git rev-parse HEAD); BR=$(git rev-parse --abbrev-ref HEAD)
PAIRS=("gs_d5a_dense gs_d5a_acmp" "gs_d5b_dense gs_d5b_acmp" "gs_d5c_dense gs_d5c_acmp")
ARMS="gs_d5a_dense gs_d5a_acmp gs_d5b_dense gs_d5b_acmp gs_d5c_dense gs_d5c_acmp"
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
    echo "D5 = cp ablation (config-only loss-balance vs D4; de-noise FIXED). engine UNCHANGED. read-out=gssem."
    echo "dev image=$(docker images --no-trunc -q jointbuildgs:dev)"
    grep -E '^(seed_protect|init_pointcloud|sem_detach_geometry|w_photo|w_sem|w_nc|w_depth|w_normal|depth_schedule|depth_warmup|w_structure|w_structure_na|w_structure_cp|structure_grouping|structure_warmup|structure_min_group|max_iter|grow_grad2d|refine_stop_iter):' "configs/tum_mob/$name.yaml"
  } > "$od/versions.txt"
done
echo "[$(date '+%F %T')] ===== D5 cp-ablation start (commit=$COMMIT branch=$BR) ====="

train_one(){  # $1=config name  $2=host GPU
  if [ -f "$OUT/$1/ckpt/final.pt" ]; then echo "[$(date '+%F %T')] SKIP train $1"; return; fi
  echo "[$(date '+%F %T')] TRAIN $1 on host-GPU$2"
  docker compose run --rm -T -e NVIDIA_VISIBLE_DEVICES=$2 dev python -m src.stage2.train \
      --config "$WS/configs/tum_mob/$1.yaml" > "$OUT/train_$1.log" 2>&1
  echo "$?" > "$OUT/$1.train.done"
}

# 1) TRAIN — 3 sequential 2-GPU pairs (dense GPU1 | acmp GPU0), mirroring D4's allocation
for pair in "${PAIRS[@]}"; do
  set -- $pair  # $1=dense $2=acmp
  echo "[$(date '+%F %T')] ----- pair: $1 (GPU1) | $2 (GPU0) -----"
  train_one "$1" 1 & P0=$!
  train_one "$2" 0 & P1=$!
  wait $P0 $P1
  echo "[$(date '+%F %T')] pair done ($1 rc=$(cat "$OUT/$1.train.done" 2>/dev/null) $2 rc=$(cat "$OUT/$2.train.done" 2>/dev/null))"
done
echo "[$(date '+%F %T')] ===== training done ====="

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

# 3) EVAL — gssem (D5 read-out) AND smrf (isolate training-prior effect), matched+orig
CFG=""
for name in $ARMS; do CFG="$CFG $name=$OUT/tsdf_$name.npz"; done
echo "[$(date '+%F %T')] EVAL gssem (GS-semantic read-out)"
python3 phases/p2-gsjso/scripts/tum_mob_eval.py --configs $CFG --geojson "$GEOJSON" \
  --classifier gssem --out "$OUT/eval_d5_gssem.json" > "$OUT/eval_d5_gssem.log" 2>&1
echo "[$(date '+%F %T')] EVAL smrf (control read-out)"
python3 phases/p2-gsjso/scripts/tum_mob_eval.py --configs $CFG --geojson "$GEOJSON" \
  --classifier smrf --out "$OUT/eval_d5_smrf.json" > "$OUT/eval_d5_smrf.log" 2>&1
echo "[$(date '+%F %T')] ===== D5 DONE ====="
