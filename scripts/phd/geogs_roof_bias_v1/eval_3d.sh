#!/usr/bin/env bash
# Filled version of official scripts/eval_3d.sh; GT is supplied already transformed.
set -euo pipefail
condition=$1
base="/task/conditions/$condition/evaluation"
# py4dgeo creates py4dgeo.log in the working directory; source is immutable.
cd "$base"
python /audit/run_seeded.py /source/evaluation/mesh2pcd.py --mesh_path "$base/fuse_post_cropped.ply" --output_path "$base/pred_points.ply"
python /source/evaluation/eval_full.py --gt_path "$base/gt_cropped.ply" --eval_path "$base/pred_points.ply" --output_root "$base/native_results"
python /source/evaluation/eval_f1.py --gt_path "$base/gt_cropped.ply" --eval_path "$base/pred_points.ply" --output_root "$base/native_results"
