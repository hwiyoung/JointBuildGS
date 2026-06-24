#!/usr/bin/env bash
# Experiment D (전체 prior 수트) — Phase 1, Lever 1 INPUT generation.
# Run COLMAP PatchMatch stereo on the EXISTING P0 colmap_dense workspace to produce
# per-view depth+normal maps (.geometric.bin) for L_depth / L_normal supervision.
#
# WHY this workspace: results/tum_transfer/data/sparse/0/{cameras,images,points3D}.bin are
# SYMLINKS into phases/p0-audit/.../colmap_dense/sparse, and data_geoidfix/images ->
# colmap_dense/images. So the GS model trained on EXACTLY these cameras+images =>
# stereo maps here are frame-correct by construction (no extrinsic mismatch).
#
# CUDA: the dev image's apt colmap is CPU-only and cannot run patch_match_stereo, so this
# uses the official colmap/colmap:latest (GPU). Run from HOST. EPSG:25832 (geo-invariant here).
#
# max_image_size 1600 = runtime/quality knob ONLY: dataloader._load_depth resizes the .bin
# to the (full-res) image dims (src/stage2/dataloader.py:180), so coarser maps upsample;
# correctness (frame/scale) is unaffected. Raise to 4096 for max fidelity (~slower).
set -euo pipefail

REPO=$(cd "$(dirname "$0")/../../.." && pwd)
MOUNT_DATA=/media/innopam/InnoPAM-8TB
DENSE_HOST="$REPO/phases/p0-audit/data/work/mvs/colmap_dense"
DENSE=/workspace/JointBuildGS/phases/p0-audit/data/work/mvs/colmap_dense
GPU="${GPU:-1}"
MAXSZ="${MAXSZ:-1024}"     # runtime/quality knob (dataloader upsamples to full res); 1024 ≈ ~1.7h/937 imgs
ITERS="${ITERS:-3}"        # patch-match iterations (5 = COLMAP default; 3 = faster, fine for a prior)
CMAP_IMG=colmap/colmap:latest

DOCKER_RUN=(docker run --rm --gpus "\"device=$GPU\""
  -v "$REPO":/workspace/JointBuildGS
  -v "$MOUNT_DATA":"$MOUNT_DATA"
  -w /workspace/JointBuildGS
  "$CMAP_IMG")

echo "[prior_full_stereo] workspace=$DENSE_HOST gpu=$GPU max_image_size=$MAXSZ"
N_IMG=$(ls "$DENSE_HOST/images" | wc -l)
echo "[prior_full_stereo] $N_IMG undistorted images to stereo"

if [ -n "$(ls -A "$DENSE_HOST/stereo/depth_maps" 2>/dev/null | grep geometric || true)" ]; then
  echo "[prior_full_stereo] depth_maps already populated — skip (delete to re-run)"
else
  echo "[prior_full_stereo] running patch_match_stereo (geom_consistency, filter, $ITERS iters)..."
  "${DOCKER_RUN[@]}" colmap patch_match_stereo \
    --workspace_path "$DENSE" --workspace_format COLMAP \
    --PatchMatchStereo.geom_consistency true \
    --PatchMatchStereo.max_image_size "$MAXSZ" \
    --PatchMatchStereo.num_iterations "$ITERS" \
    --PatchMatchStereo.filter true \
    --PatchMatchStereo.cache_size 32
fi

ND=$(ls "$DENSE_HOST/stereo/depth_maps" 2>/dev/null | grep -c geometric || true)
NN=$(ls "$DENSE_HOST/stereo/normal_maps" 2>/dev/null | grep -c geometric || true)
echo "[prior_full_stereo] depth .geometric.bin: $ND   normal .geometric.bin: $NN"

# Stage stereo/ under the v6 data_root so dataloader._find_depth/_find_normal resolve it.
DR_HOST="$REPO/results/tum_transfer/data_geoidfix"
if [ ! -e "$DR_HOST/stereo" ]; then
  # RELATIVE symlink so it resolves both on host and inside the dev container (which mounts the
  # repo at /workspace/JointBuildGS but the InnoPAM-8TB host root at /data, not its host path).
  ln -s ../../../phases/p0-audit/data/work/mvs/colmap_dense/stereo "$DR_HOST/stereo"
  echo "[prior_full_stereo] symlinked (relative) $DR_HOST/stereo -> colmap_dense/stereo"
else
  echo "[prior_full_stereo] $DR_HOST/stereo already exists"
fi

# Reproducibility: record colmap version + params.
VER=$("${DOCKER_RUN[@]}" colmap --help 2>&1 | head -1 || echo "colmap/colmap:latest")
echo "[prior_full_stereo] DONE. colmap=$VER max_image_size=$MAXSZ geom_consistency=true iters=5"
