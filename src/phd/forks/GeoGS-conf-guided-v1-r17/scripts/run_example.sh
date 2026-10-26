#!/usr/bin/env bash
# Runs the full GeoGS pipeline (train -> render -> 2D metrics -> 3D evaluation) on the
# downloadable example scene. See README.md > Example Data for the download link.
#
# Usage: bash scripts/run_example.sh <path_to_example_scene>

set -e

SCENE_DIR="${1:?Usage: bash scripts/run_example.sh <path_to_example_scene>}"
OUTPUT_DIR="output/example_scene_geogs"
RESULTS_DIR="evaluation_data/results"

python train.py \
  -s "$SCENE_DIR" -m "$OUTPUT_DIR" \
  --lod_depth_path "$SCENE_DIR/lod2_prior" \
  --da_depth_path "$SCENE_DIR/da3_prior" \
  --lod2_pcd_path "$SCENE_DIR/lod2_pcd.ply" \
  --eval --lod_init --freeze_onlybldg --protect_bldg --dynamic_depth_weight

python render.py -s "$SCENE_DIR" -m "$OUTPUT_DIR" --iteration 30000 --mesh_res 1024

python metrics.py -m "$OUTPUT_DIR"

# The bundled ground truth is already transformed into the scene's local frame, so
# evaluation/transform_gt_pcd.py is not needed here (no reference frame is shipped either).
mkdir -p "$RESULTS_DIR"
python evaluation/mesh2pcd.py \
  --mesh_path "$OUTPUT_DIR/train/ours_30000/fuse_post.ply" \
  --output_path "$RESULTS_DIR/pred_points.ply"
python evaluation/eval_full.py \
  --gt_path "$SCENE_DIR/ground_truth/r1_b1_sub002_transformed.ply" \
  --eval_path "$RESULTS_DIR/pred_points.ply" --output_root "$RESULTS_DIR"
python evaluation/eval_f1.py \
  --gt_path "$SCENE_DIR/ground_truth/r1_b1_sub002_transformed.ply" \
  --eval_path "$RESULTS_DIR/pred_points.ply" --output_root "$RESULTS_DIR"
