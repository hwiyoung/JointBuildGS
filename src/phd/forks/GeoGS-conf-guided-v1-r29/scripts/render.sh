#!/usr/bin/env bash
# Render held-out test views and extract a mesh from a trained GeoGS model.

set -e

SCENE_DIR="<path_to_scene>"           # same -s used for training
MODEL_DIR="output/<experiment_name>"  # same -m used for training

python render.py \
  -s "$SCENE_DIR" \
  -m "$MODEL_DIR" \
  --iteration 30000 \
  --voxel_size 0.004 \
  --depth_trunc 3.0 \
  --sdf_trunc 0.02 \
  --mesh_res 1024

python metrics.py -m "$MODEL_DIR"
