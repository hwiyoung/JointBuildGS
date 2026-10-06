#!/usr/bin/env bash
# Example training command for GeoGS
# Replace the placeholder paths below with your own.
#
# Expected inputs (see README.md > Data Preparation):
#   <scene_dir>/sparse/0/{cameras,images,points3D}.bin              - COLMAP poses
#   <lod2_prior_dir>/raw_depth/<image_name>.npy                     - LoD2 structural depth (LoD2Depth/main.py)
#   <da3_prior_dir>/raw_depth/<image_name>.npy                      - DA3 visual depth (preprocessing/get_da3_depth_with_colmap.py)
#   <lod2_pcd.ply>                                                  - dense LoD2 surface point cloud (data/generate_pcd.py)

set -e

SCENE_DIR="<path_to_scene>"                 # e.g. data/building1/building1_15
OUTPUT_DIR="output/<experiment_name>"        # e.g. output/building1_geogs
LOD2_DEPTH_PATH="<path_to_lod2_prior>"       # e.g. ${SCENE_DIR}/lod2_prior
DA3_DEPTH_PATH="<path_to_da3_prior>"         # e.g. ${SCENE_DIR}/da3_prior
LOD2_PCD_PATH="<path_to_lod2_pcd.ply>"       # e.g. ${SCENE_DIR}/lod2_pcd.ply

python train.py \
  -s "$SCENE_DIR" \
  -m "$OUTPUT_DIR" \
  --lod_depth_path "$LOD2_DEPTH_PATH" \
  --da_depth_path "$DA3_DEPTH_PATH" \
  --lod2_pcd_path "$LOD2_PCD_PATH" \
  --eval \
  --lod_init \
  --freeze_onlybldg \
  --protect_bldg \
  --dynamic_depth_weight
