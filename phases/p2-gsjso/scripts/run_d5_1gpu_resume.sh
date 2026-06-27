#!/usr/bin/env bash
# P2-D5 — single-GPU RESUME after one GPU was handed to a colleague (index 0 / GPU-4bdf freed).
# Runs the rest of D5 SEQUENTIALLY on the kept dedicated card index 1 (GPU-fab8) via NVIDIA_VISIBLE_DEVICES=1.
# *** NEVER uses index 0 (colleague's). *** gs_d5b_dense is still finishing (left running) — we WAIT for it.
# Then: retrain gs_d5b_acmp (was killed to free the GPU) -> D5c dense -> D5c acmp -> TSDF(6) -> eval(gssem+smrf).
# Mirrors run_d5.sh post-train steps. Idempotent (skips arms/extracts already done). EPSG:25832.
# Launch: setsid nohup bash phases/p2-gsjso/scripts/run_d5_1gpu_resume.sh > results/tum_transfer/mob/d5_1gpu.log 2>&1 < /dev/null &
set -u
cd "$(dirname "$0")/../../.." || exit 1
REPO_HOST="$(pwd -P)"; WS=/workspace/JointBuildGS
OUT=results/tum_transfer/mob
GPU=1   # NVIDIA_VISIBLE_DEVICES=1 -> host index 1 = GPU-fab8 (dedicated). index 0 = colleague's, untouched.
GEOJSON=results/tum_transfer/analysis/footprints_aoi.geojson
ALL="gs_d5a_dense gs_d5a_acmp gs_d5b_dense gs_d5b_acmp gs_d5c_dense gs_d5c_acmp"
COMMIT=$(git rev-parse HEAD); BR=$(git rev-parse --abbrev-ref HEAD)
rm -f "$OUT/D5_1GPU_DONE"
echo "[resume-1gpu] start $(date '+%F %T') GPU=index$GPU(GPU-fab8). colleague=index0. commit=$COMMIT"

# 1) wait for the still-running gs_d5b_dense to finish (do NOT touch it)
echo "[resume-1gpu] waiting for gs_d5b_dense final.pt ..."
while [ ! -f "$OUT/gs_d5b_dense/ckpt/final.pt" ]; do sleep 30; done
echo "[resume-1gpu] $(date '+%T') gs_d5b_dense done."

# 2) clean partial gs_d5b_acmp (killed to free GPU; root-owned -> remove via docker)
docker compose run --rm -T dev bash -lc "rm -rf $WS/$OUT/gs_d5b_acmp" >/dev/null 2>&1
echo "[resume-1gpu] cleaned partial gs_d5b_acmp"

train_one(){  # $1 = config name
  if [ -f "$OUT/$1/ckpt/final.pt" ]; then echo "[$(date '+%T')] SKIP train $1"; return; fi
  od="$OUT/$1"; mkdir -p "$od"
  { echo "run=$1 stamped=$(date '+%F %T') git=$COMMIT branch=$BR (1-GPU resume, NVIDIA_VISIBLE_DEVICES=$GPU=GPU-fab8)"
    echo "datum: GS-LOCAL=EPSG:25832-[690953,5336071,604]; acmp seed -556 (geoid)"
    grep -E '^(w_structure_cp|structure_warmup|w_depth|w_normal|w_structure_na|max_iter):' "configs/tum_mob/$1.yaml"
  } > "$od/versions.txt"
  echo "[$(date '+%T')] TRAIN $1 (index$GPU)"
  docker compose run --rm -T -e NVIDIA_VISIBLE_DEVICES=$GPU dev python -m src.stage2.train \
      --config "$WS/configs/tum_mob/$1.yaml" > "$OUT/train_$1.log" 2>&1
  echo "$?" > "$OUT/$1.train.done"
}

# 3) sequential training on the single kept GPU
for n in gs_d5b_acmp gs_d5c_dense gs_d5c_acmp; do train_one "$n"; done
echo "[resume-1gpu] $(date '+%T') training done"

# 4) TSDF extract all 6 (semantic), sequential on index$GPU
for n in $ALL; do
  [ -f "$OUT/tsdf_$n.npz" ] && { echo "SKIP extract $n"; continue; }
  [ -f "$OUT/$n/ckpt/final.pt" ] || { echo "NO ckpt $n"; continue; }
  echo "[$(date '+%T')] EXTRACT $n"
  docker compose run --rm -T -e NVIDIA_VISIBLE_DEVICES=$GPU dev python phases/p2-gsjso/scripts/tum_mob_tsdf_extract.py \
      --ckpt "$WS/$OUT/$n/ckpt/final.pt" --out "$WS/$OUT/tsdf_$n.npz" \
      --min-obs 3 --voxel 0.05 --downscale 1.0 > "$OUT/extract_$n.log" 2>&1
done

# 5) eval gssem + smrf (CPU/docker)
CFG=""; for n in $ALL; do CFG="$CFG $n=$OUT/tsdf_$n.npz"; done
echo "[$(date '+%T')] EVAL gssem"; python3 phases/p2-gsjso/scripts/tum_mob_eval.py --configs $CFG --geojson "$GEOJSON" --classifier gssem --out "$OUT/eval_d5_gssem.json" > "$OUT/eval_d5_gssem.log" 2>&1
echo "[$(date '+%T')] EVAL smrf";  python3 phases/p2-gsjso/scripts/tum_mob_eval.py --configs $CFG --geojson "$GEOJSON" --classifier smrf  --out "$OUT/eval_d5_smrf.json"  > "$OUT/eval_d5_smrf.log"  2>&1
echo "[resume-1gpu] DONE $(date '+%F %T')" | tee "$OUT/D5_1GPU_DONE"
