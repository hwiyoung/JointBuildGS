# Visual Depth Preprocessing (Depth-Anything-3)

GeoGS's Refinement Stage (Sec. 3.4.2 of the paper) supervises with dense, pose-conditioned
visual depth produced offline by [Depth-Anything-3 (DA3)](https://github.com/ByteDance-Seed/Depth-Anything-3).
This directory ships `get_da3_depth_with_colmap.py`, the script we used to run DA3 against a
COLMAP reconstruction and export per-view metric depth in the layout `train.py` expects.

## Setup

DA3 is a separate, fairly large project (model weights, its own environment) and is **not**
vendored here. Clone it (our fork adds no changes required for this script beyond upstream —
plain upstream works too) and install it in its own environment, following its README:

```bash
git clone https://github.com/ByteDance-Seed/Depth-Anything-3.git
cd Depth-Anything-3
pip install torch>=2 torchvision
pip install -e .
```

## Usage

Copy or symlink `get_da3_depth_with_colmap.py` into that DA3 checkout (or add it to `PYTHONPATH`),
then run it against your COLMAP scene:

```bash
python get_da3_depth_with_colmap.py \
  --colmap-dir <path_to_scene> \
  --output-dir <path_to_scene>/da3_prior \
  --model da3nested-giant-large \
  --sparse-subdir 0 \
  --process-res 840 \
  --upsample-to-original
```

This produces `<path_to_scene>/da3_prior/raw_depth/<image_name>.npy` — the directory to pass as
`--da_depth_path` to `train.py`. Because DA3 performs pose-conditioned inference, the
predicted depth is already in the same metric scale as the COLMAP poses, so no separate
scale-alignment step is needed (unlike monocular depth estimators).
