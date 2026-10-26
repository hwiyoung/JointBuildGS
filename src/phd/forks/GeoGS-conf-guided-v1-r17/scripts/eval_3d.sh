#!/usr/bin/env bash
# 3D geometric evaluation: align predicted mesh/point cloud to ground truth, then
# compute Chamfer Distance, M3C2, and F-score at 0.2m / 0.5m thresholds.

set -e

GT_PLY="<path_to_ground_truth.ply>"          # LiDAR point cloud (TUM2TWIN) or sampled reference mesh (egenioussBench)
REF_FRAME="<path_to_scene_reference_frame.json>"
MESH_PLY="<path_to_rendered_mesh.ply>"       # e.g. output/<experiment_name>/train/ours_30000/fuse_post.ply
RESULTS_DIR="evaluation_data/results"

mkdir -p "$RESULTS_DIR"

# 1. Bring the ground truth into the scene's local metric frame
# (skip this step if your GT is already in that frame, e.g. a filename ending in "_transformed")
python evaluation/transform_gt_pcd.py \
  --input "$GT_PLY" \
  --output "${RESULTS_DIR}/gt_transformed.ply" \
  --transform "$REF_FRAME"

# 2. Sample the extracted mesh into a point cloud for comparison
python evaluation/mesh2pcd.py \
  --mesh_path "$MESH_PLY" \
  --output_path "${RESULTS_DIR}/pred_points.ply"

# 3. Chamfer distance + traditional/voxel completeness + M3C2 surface deviation
python evaluation/eval_full.py \
  --gt_path "${RESULTS_DIR}/gt_transformed.ply" \
  --eval_path "${RESULTS_DIR}/pred_points.ply" \
  --output_root "$RESULTS_DIR"

# 4. F-score at 0.2m / 0.5m thresholds (Tanks-and-Temples style)
python evaluation/eval_f1.py \
  --gt_path "${RESULTS_DIR}/gt_transformed.ply" \
  --eval_path "${RESULTS_DIR}/pred_points.ply" \
  --output_root "$RESULTS_DIR"
