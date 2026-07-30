#!/usr/bin/env bash
# P2 Phase B / B1 — self-supervised multi-view consistency (L_mvc) re-train. 2-arm pipeline
# mirroring run_d4.sh: PARALLEL 2-GPU train (gs_b1_dense host-GPU1 | gs_b1_acmp host-GPU0)
#   -> semantic TSDF -> eval (gssem + smrf). B1 = D4 + L_mvc (the only added term). MUST-EQ otherwise.
# Baseline to compare against = gs_d4_{dense,acmp} (already trained; same harness).
# Report: docs/experiments/joint-optimization/w_phase_b_structure/reports/W_phaseB_structure.md. EPSG:25832. branch feat/p2-structure-learn.
# PREREQ: depth/normal maps staged at data_geoidfix/stereo (prior_full_stereo.sh) — same as D4
#         (B1 keeps w_depth=0.03, so the stereo maps are still required).
# Launch: setsid nohup bash phases/p2-gsjso/scripts/run_b1.sh > results/tum_transfer/mob/b1.log 2>&1 &
set -u
cd "$(dirname "$0")/../../.." || exit 1
OUT=results/tum_transfer/mob; WS=/workspace/JointBuildGS
mkdir -p "$OUT"
COMMIT=$(git rev-parse HEAD); BR=$(git rev-parse --abbrev-ref HEAD)
ARMS="gs_b1_dense gs_b1_acmp"
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
    echo "B1 = D4 + L_mvc (self-supervised multi-view geometric consistency). engine ADDITIVE vs D4. read-out=gssem."
    echo "dev image=$(docker images --no-trunc -q jointbuildgs:dev)"
    grep -E '^(seed_protect|init_pointcloud|sem_detach_geometry|w_photo|w_sem|w_nc|w_depth|w_normal|w_structure_cp|structure_grouping|structure_warmup|w_mvc|mvc_warmup|mvc_schedule|mvc_ramp_steps|mvc_every|mvc_neighbor_k|mvc_max_angle_deg|mvc_min_baseline|mvc_w_normal|mvc_ref_detach|max_iter):' "configs/tum_mob/$name.yaml"
  } > "$od/versions.txt"
done
echo "[$(date '+%F %T')] ===== B1 L_mvc re-train start (commit=$COMMIT branch=$BR) ====="

train_one(){  # $1=config name  $2=host GPU
  if [ -f "$OUT/$1/ckpt/final.pt" ]; then echo "[$(date '+%F %T')] SKIP train $1"; return; fi
  echo "[$(date '+%F %T')] TRAIN $1 on host-GPU$2"
  docker compose run --rm -T -e NVIDIA_VISIBLE_DEVICES=$2 dev python -m src.stage2.train \
      --config "$WS/configs/tum_mob/$1.yaml" > "$OUT/train_$1.log" 2>&1
  echo "$?" > "$OUT/$1.train.done"
}

# 1) PARALLEL train on 2 GPUs
train_one gs_b1_dense 1 & P0=$!
train_one gs_b1_acmp  0 & P1=$!
wait $P0 $P1
echo "[$(date '+%F %T')] ===== training done (dense rc=$(cat "$OUT/gs_b1_dense.train.done" 2>/dev/null) acmp rc=$(cat "$OUT/gs_b1_acmp.train.done" 2>/dev/null)) ====="

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

# 3) EVAL — gssem (B1 read-out) AND smrf (control), matched+orig
CFG="gs_b1_dense=$OUT/tsdf_gs_b1_dense.npz gs_b1_acmp=$OUT/tsdf_gs_b1_acmp.npz"
echo "[$(date '+%F %T')] EVAL gssem (GS-semantic read-out)"
python3 phases/p2-gsjso/scripts/tum_mob_eval.py --configs $CFG --geojson "$GEOJSON" \
  --classifier gssem --out "$OUT/eval_b1_gssem.json" > "$OUT/eval_b1_gssem.log" 2>&1
echo "[$(date '+%F %T')] EVAL smrf (control read-out)"
python3 phases/p2-gsjso/scripts/tum_mob_eval.py --configs $CFG --geojson "$GEOJSON" \
  --classifier smrf --out "$OUT/eval_b1_smrf.json" > "$OUT/eval_b1_smrf.log" 2>&1
echo "[$(date '+%F %T')] ===== B1 DONE ====="
