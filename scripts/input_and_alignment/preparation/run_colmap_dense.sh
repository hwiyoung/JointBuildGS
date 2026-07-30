#!/usr/bin/env bash
# COLMAP PatchMatch MVS for seongsu — runs via the official colmap/colmap:latest
# (CUDA-enabled). The dev container's apt colmap is CPU-only and cannot run
# patch_match_stereo.
#
# Usage (from HOST, not inside dev container):
#   bash scripts/input_and_alignment/preparation/run_colmap_dense.sh
#
# Inputs:
#   /media/innopam/InnoPAM-8TB/hwiyoung/code/thin-recon/data/colmap_export/{cameras,images,points3D}.txt
#   /media/innopam/InnoPAM-8TB/data/seongsu/images/high/*.JPG
# Outputs:
#   <REPO>/data/seongsu/colmap/sparse/*.bin
#   <REPO>/data/seongsu/colmap/dense/images/
#   <REPO>/data/seongsu/colmap/dense/sparse/
#   <REPO>/data/seongsu/colmap/dense/stereo/{depth_maps,normal_maps}/*.geometric.bin

set -euo pipefail

REPO=$(cd "$(dirname "$0")/../../.." && pwd)
MOUNT_DATA=/media/innopam/InnoPAM-8TB

SPARSE_TXT_HOST=$REPO/data/seongsu/colmap_rescaled  # 8192x5460 rescaled from 8270x5476 calibration
IMG_HOST=$REPO/data/seongsu/images_colmap  # symlinks: names match colmap images.txt
WORK_HOST=$REPO/data/seongsu/colmap

mkdir -p "$WORK_HOST/sparse" "$WORK_HOST/dense" "$WORK_HOST/_sparse_txt"

# Stage sparse txt for model_converter.
cp "$SPARSE_TXT_HOST"/cameras.txt "$SPARSE_TXT_HOST"/images.txt "$SPARSE_TXT_HOST"/points3D.txt "$WORK_HOST/_sparse_txt/"

CMAP_IMG=colmap/colmap:latest
DOCKER_RUN=(docker run --rm --gpus '"device=1"'
  -v "$REPO":/workspace/JointBuildGS
  -v "$MOUNT_DATA":/data
  -v "$MOUNT_DATA":"$MOUNT_DATA"   # identical host path so absolute symlinks resolve
  -w /workspace/JointBuildGS
  "$CMAP_IMG")

WORK=/workspace/JointBuildGS/data/seongsu/colmap
SPARSE_BIN=$WORK/sparse
DENSE=$WORK/dense
IMG_DIR=/workspace/JointBuildGS/data/seongsu/images_colmap
SPARSE_TXT=$WORK/_sparse_txt

echo "[1/3] Convert sparse txt -> binary"
if [ ! -f "$WORK_HOST/sparse/cameras.bin" ]; then
  "${DOCKER_RUN[@]}" colmap model_converter \
    --input_path "$SPARSE_TXT" --output_path "$SPARSE_BIN" --output_type BIN
else
  echo "  (skip)"
fi

echo "[2/3] image_undistorter (max 4096)"
if [ ! -d "$WORK_HOST/dense/images" ] || [ -z "$(ls -A "$WORK_HOST/dense/images" 2>/dev/null)" ]; then
  "${DOCKER_RUN[@]}" colmap image_undistorter \
    --image_path "$IMG_DIR" --input_path "$SPARSE_BIN" \
    --output_path "$DENSE" --output_type COLMAP --max_image_size 4096
else
  echo "  (skip)"
fi

echo "[3/3] patch_match_stereo (depth + normal)"
if [ ! -d "$WORK_HOST/dense/stereo/depth_maps" ] || [ -z "$(ls -A "$WORK_HOST/dense/stereo/depth_maps" 2>/dev/null)" ]; then
  "${DOCKER_RUN[@]}" colmap patch_match_stereo \
    --workspace_path "$DENSE" --workspace_format COLMAP \
    --PatchMatchStereo.geom_consistency true \
    --PatchMatchStereo.max_image_size 4096 \
    --PatchMatchStereo.num_iterations 5 \
    --PatchMatchStereo.filter true \
    --PatchMatchStereo.cache_size 32
else
  echo "  (skip)"
fi

echo "---"
echo "depth maps:  $(ls "$WORK_HOST/dense/stereo/depth_maps" 2>/dev/null | grep -c geometric || true)"
echo "normal maps: $(ls "$WORK_HOST/dense/stereo/normal_maps" 2>/dev/null | grep -c geometric || true)"
echo "Done."
