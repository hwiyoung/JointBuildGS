#!/usr/bin/env bash
# P2 make-or-break C — seed-protect 2-arm pipeline: PARALLEL 2-GPU train -> TSDF -> matched eval.
# De-confounds v6 (which pruned MVS seeds to 0 on low-density buildings). Same eval harness as v6;
# raw/LiDAR/ref reused from v6 for the 8-way. Engine change isolated on branch feature/p2-seed-protect.
# Launch: setsid nohup bash scripts/input_and_alignment/tum_transfer/run_mob_v6_protect.sh > results/tum_transfer/mob/v6_protect.log 2>&1 &
# dev service = host GPU1 (NVIDIA_VISIBLE_DEVICES=1); 2nd arm overridden to host GPU0. EPSG:25832.
set -u
cd "$(dirname "$0")/../../.." || exit 1
OUT=results/tum_transfer/mob; WS=/workspace/JointBuildGS
mkdir -p "$OUT"
COMMIT=$(git rev-parse HEAD); BR=$(git rev-parse --abbrev-ref HEAD)
ARMS="gs_seed_dense_protect gs_seed_acmp_protect"

for name in $ARMS; do
  od="$OUT/$name"; mkdir -p "$od"
  {
    echo "run=$name  stamped=$(date '+%F %T')  git=$COMMIT  branch=$BR"
    echo "datum: GS-LOCAL=EPSG:25832-[690953,5336071,604]; dim seed -604, acmp -556 (geoid)"
    echo "seed_protect=true (MVS seeds + lineage exempt from opacity-prune); v6 densification otherwise"
    echo "dev image=$(docker images --no-trunc -q jointbuildgs:dev)  roofer=3dgi/roofer@sha256:dd2c415a..."
    grep -E '^(seed_protect|init_pointcloud|init_pointcloud_mode|sem_detach_geometry|w_sem|w_structure|w_mutual|w_depth|w_normal|max_iter|grow_grad2d|refine_every|refine_stop_iter):' "configs/input_and_alignment/tum_mob/$name.yaml"
  } > "$od/versions.txt"
done
echo "[$(date '+%F %T')] ===== C seed-protect start (commit=$COMMIT branch=$BR) ====="

train_one(){  # $1=config name  $2=host GPU (NVIDIA_VISIBLE_DEVICES)
  if [ -f "$OUT/$1/ckpt/final.pt" ]; then echo "[$(date '+%F %T')] SKIP train $1"; return; fi
  echo "[$(date '+%F %T')] TRAIN $1 on host-GPU$2"
  docker compose run --rm -T -e NVIDIA_VISIBLE_DEVICES=$2 dev python -m src.stage2.train \
      --config "$WS/configs/input_and_alignment/tum_mob/$1.yaml" > "$OUT/train_$1.log" 2>&1
  echo "$?" > "$OUT/$1.train.done"
}

# 1) PARALLEL train on 2 GPUs
train_one gs_seed_dense_protect 1 & P0=$!
train_one gs_seed_acmp_protect  0 & P1=$!
wait $P0 $P1
echo "[$(date '+%F %T')] ===== training done (dense rc=$(cat "$OUT/gs_seed_dense_protect.train.done" 2>/dev/null) acmp rc=$(cat "$OUT/gs_seed_acmp_protect.train.done" 2>/dev/null)) ====="

# 2) EXTRACT TSDF (sequential, default GPU1)
for name in $ARMS; do
  [ -f "$OUT/tsdf_$name.npz" ] && { echo "[$(date '+%F %T')] SKIP extract $name"; continue; }
  [ -f "$OUT/$name/ckpt/final.pt" ] || { echo "[$(date '+%F %T')] NO ckpt $name"; continue; }
  echo "[$(date '+%F %T')] EXTRACT $name"
  docker compose run --rm -T dev python scripts/stage3_readout/tum_mob_tsdf_extract.py \
      --ckpt "$WS/$OUT/$name/ckpt/final.pt" --out "$WS/$OUT/tsdf_$name.npz" \
      --min-obs 3 --voxel 0.05 --downscale 1.0 > "$OUT/extract_$name.log" 2>&1
  echo "$?" > "$OUT/$name.extract.done"
done

# 3) EVAL (matched, identical harness to v6)
echo "[$(date '+%F %T')] EVAL (matched)"
python3 scripts/input_and_alignment/tum_transfer/tum_mob_eval.py \
  --configs gs_seed_dense_protect="$OUT/tsdf_gs_seed_dense_protect.npz" \
            gs_seed_acmp_protect="$OUT/tsdf_gs_seed_acmp_protect.npz" \
  --out "$OUT/eval_v6_protect.json" > "$OUT/eval_v6_protect.log" 2>&1
echo "$?" > "$OUT/eval_v6_protect.done"
touch "$OUT/V6_PROTECT_DONE"
echo "[$(date '+%F %T')] ===== C ALL DONE (eval rc=$(cat "$OUT/eval_v6_protect.done")) ====="
