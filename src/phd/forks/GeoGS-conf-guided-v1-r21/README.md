# GeoGS: Geometric Prior-Guided Gaussian Splatting for Robust Urban Reconstruction from Sparse Views

[Paper](https://www.sciencedirect.com/science/article/pii/S0924271626003588) (ISPRS Journal of Photogrammetry and Remote Sensing)

Qilin Zhang<sup>1,2</sup>, Olaf Wysocki<sup>3</sup>, Boris Jutzi<sup>1,2</sup>

<sup>1</sup> Photogrammetry and Remote Sensing, Karlsruhe Institute of Technology
<sup>2</sup> Photogrammetry and Remote Sensing, Technical University of Munich
<sup>3</sup> CV4DT, University of Cambridge

<p align="center">
  <img src="media/teaser_rev_fin.png" alt="GeoGS teaser" width="100%">
</p>

## Abstract

Gaussian Splatting (GS) has emerged as an efficient representation for large-scale urban reality capture, yet reliable reconstruction in complex built environments typically requires dense image collections with high view overlap. Under sparse observations, it often yields geometrically inaccurate and incomplete reconstructions, making external geometric priors essential for robust optimization. Geo-referenced 3D city models provide complete and metrically reliable structural priors but lack fine as-built details, whereas visual foundation models infer dense local geometric cues from images yet remain less reliable in occluded, weakly textured, or sparsely observed regions.

We present GeoGS, a geometry-aware GS method that integrates worldwide-available CityGML Level of Detail (LoD) 2 models with pose-conditioned depth cues from visual foundation models for robust urban reconstruction from sparse views with known camera poses. It initializes Gaussians directly from LoD2 surfaces and optimizes them in two stages. In the **Anchoring Stage**, depth rendered from the 3D city model establishes a metrically consistent building backbone, while a proximity-based geometry protection mechanism prevents structural drift. In the **Refinement Stage**, dense visual depth is introduced with a lightweight structural anchor and adaptive weighting to recover local geometric details without compromising the established topology.

Experiments on the UAV-based TUM2TWIN dataset and the street-level egenioussBench dataset demonstrate consistent improvements over state-of-the-art baselines. On TUM2TWIN, GeoGS improves average PSNR by 1.13 dB in 2D rendering assessment and reduces extracted-mesh M3C2 distance by 14.3% in 3D geometric evaluation, compared with the respective best-performing baselines. These results highlight the effectiveness of integrating structured geospatial priors with data-driven visual cues, advancing sparse-view Gaussian Splatting toward scalable and geometrically reliable urban digital twin generation.

## News

- **[2026-07]** GeoGS is accepted by the ISPRS Journal of Photogrammetry and Remote Sensing. 🎉
- **[2026-08]** Code release.

## Method Overview

- **LoD2-based initialization**: Gaussians are seeded directly on the CityGML LoD2 building mesh through face-area-weighted sampling and per-view visibility raycasting, avoiding fragile SfM point clouds.
- **Two depth priors**: an occlusion-free but architecturally coarse structural depth rendered from the LoD2 mesh, and a dense, pose-conditioned visual depth from Depth-Anything-3.
- **Two-stage optimization**: the Anchoring Stage supervises with LoD2 depth and protects building Gaussians through proximity-based gradient attenuation; the Refinement Stage introduces the visual depth alongside a lightweight LoD2 anchor, with an adaptive dual-gated weight decay that relaxes geometric regularization once it is no longer needed.

See the paper's Methodology section for the full derivation.

## Installation

Tested with Python 3.10.20, PyTorch 2.1.2 (cu121 build), and a CUDA 12.4 toolkit for compiling
the CUDA submodules below.

```bash
git clone --recursive https://github.com/zqlin0521/GeoGS.git
cd GeoGS
# if you cloned without --recursive:
git submodule update --init --recursive

# conda provides python=3.10.20 and a matching pip/setuptools; everything else is installed with pip
conda env create -f environment.yml
conda activate geogs

pip install torch==2.1.2 torchvision==0.16.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt

# --no-build-isolation lets these see the torch already installed above;
# without it, pip builds them in an isolated env with no torch and the compile fails
pip install submodules/diff-surfel-rasterization --no-build-isolation
pip install submodules/simple-knn --no-build-isolation
```

Adjust the `cu121` index URL to match your CUDA toolkit (see the
[PyTorch install matrix](https://pytorch.org/get-started/previous-versions/#v212)).

## Data Preparation

GeoGS expects, for each scene, calibrated camera poses in COLMAP format
(`<scene_dir>/sparse/0/{cameras,images,points3D}.bin` and `<scene_dir>/images/`) and a
geo-referenced LoD2 building mesh aligned to the same local coordinate frame as the poses.

1. **Camera poses**: any SfM/photogrammetry pipeline that outputs COLMAP-format poses works.
2. **LoD2-guided Gaussian initialization**: sample and visibility-filter points on the aligned
   LoD2 mesh (Sec. 3.2 of the paper):
   ```bash
   python data/generate_pcd.py \
     --mesh_path <lod2_mesh.obj> \
     --reference_frame_path <scene_reference_frame.json> \
     --colmap_dir <scene_dir>/sparse_txt \
     --output_dir <scene_dir>/sparse_lod/0
   ```
3. **LoD2 structural depth** (raycasting the mesh into each view, Sec. 3.3.1):
   ```bash
   cd LoD2Depth
   python main.py \
     --mesh_path <lod2_mesh.obj> \
     --reference_frame_path <scene_reference_frame.json> \
     --colmap_dir <scene_dir>/sparse_txt \
     --building_name <scene_name> \
     --generate_maps
   ```
   Produces `<scene_dir>/lod2_prior/raw_depth/*.npy`, passed as `--lod_depth_path`.
4. **DA3 visual depth** (Sec. 3.3.2): see [`preprocessing/README.md`](preprocessing/README.md).
   Produces `<scene_dir>/da3_prior/raw_depth/*.npy`, passed as `--da_depth_path`.

## Training

```bash
python train.py \
  -s <scene_dir> \
  -m output/<experiment_name> \
  --lod_depth_path <scene_dir>/lod2_prior \
  --da_depth_path <scene_dir>/da3_prior \
  --lod2_pcd_path <scene_dir>/lod2_pcd.ply \
  --eval \
  --lod_init \
  --freeze_onlybldg \
  --protect_bldg \
  --dynamic_depth_weight
```

`--lod2_match_thresh` (τ=0.2m), `--lambda_lod_anchor` (0.005), `--protect_bldg_lr_scale` (0.01),
`--lod2_building_xyz_lr_scale` (0.01), `--stage_switch_iter` (8000), and `--save_iterations`
(8000 30000) are not passed above because they already match the paper-consistent defaults in
`train.py`. See `scripts/train.sh` for an annotated template, and `python train.py --help` for
the full argument list, including dual-gated decay hyperparameters such as
`--depth_guard_threshold`, `--rgb_benefit_threshold`, and `--depth_decay_factor`.
Trained on a single NVIDIA RTX 4090 for 30,000 iterations, with identical hyperparameters
across all reported scenes and datasets (no per-scene tuning).

## Rendering and Evaluation

```bash
# render test views + extract mesh
python render.py -s <scene_dir> -m output/<experiment_name> --iteration 30000 --mesh_res 1024

# 2D novel-view synthesis metrics (PSNR / SSIM / LPIPS)
python metrics.py -m output/<experiment_name>

# 3D geometric evaluation (Chamfer / M3C2 / F-score against LiDAR or a reference mesh)
bash scripts/eval_3d.sh
```

See `scripts/render.sh` and `scripts/eval_3d.sh` for templates.

> **Note:** when evaluating a single building extracted from a larger scene, crop the rendered
> mesh (`fuse_post.ply`) to the building's region of interest before running `mesh2pcd.py` and
> the evaluation scripts (e.g. with CloudCompare or Open3D), so metrics are not diluted by
> surrounding ground or context geometry.

## Datasets

- **[TUM2TWIN](https://tum2t.win/)** (UAV, aerial): co-registered CityGML LoD2 models and
  UAV-borne LiDAR ground truth of the TU Munich campus.
- **[egenioussBench](https://github.com/fratopa/egenioussBench)** (street-level, terrestrial):
  Braunschweig, Germany, with CityGML LoD2 models and a high-fidelity oblique-imagery reference mesh.

## Example Data

A ready-to-use example scene (15 UAV views of a single building, COLMAP poses, LoD2-guided
initialization, LoD2 structural depth, DA3 visual depth, the LoD2 point cloud for building
protection, and a ground-truth point cloud for 3D evaluation) is available so you can try the
full pipeline without running the data preparation steps above.

**[Download example_scene.zip (Google Drive)](https://drive.google.com/file/d/1QPp349lFSuBiyfcJBbcG3eIweiVt_Etp/view?usp=sharing)**

Unzip it, then run:

```bash
bash scripts/run_example.sh <path_to>/example_scene
```

This trains, renders, and evaluates the scene end to end. See `scripts/run_example.sh` for the
individual commands.

## Citation

```bibtex
@article{zhang2026geogs,
  title={GeoGS: Geometric Prior-Guided Gaussian Splatting for Robust Urban Reconstruction from Sparse Views},
  author={Zhang, Qilin and Wysocki, Olaf and Jutzi, Boris},
  journal={ISPRS Journal of Photogrammetry and Remote Sensing},
  year={2026}
}
```

## Acknowledgements

This codebase builds on [2D Gaussian Splatting](https://github.com/hbb1/2d-gaussian-splatting).
Visual depth priors are extracted with
[Depth-Anything-3](https://github.com/ByteDance-Seed/Depth-Anything-3). We gratefully acknowledge
the [TUM2TWIN](https://tum2t.win/) and [egenioussBench](https://github.com/fratopa/egenioussBench)
teams for making their datasets publicly available, without which the evaluation in this work
would not have been possible.

## License

See [LICENSE.md](LICENSE.md) (Gaussian-Splatting non-commercial research license, inherited from
Inria/MPII's original 2D/3D Gaussian Splatting code). The bundled `submodules/` (rasterizer and
simple-knn) carry their own licenses; see their respective repositories.
