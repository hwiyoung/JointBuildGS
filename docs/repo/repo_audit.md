# Repository Audit Before GS-JSO Implementation

Snapshot date: 2026-06-05  
Branch: `fc/current-baseline-cleanup`  
Scope: lightweight inspection only. No files were deleted, no data was downloaded, and no training was run.

## Verification Commands

Commands used:

- `git status --short --branch`
- `find . -maxdepth 2 -mindepth 1 -not -path './.git*' -printf '%y %p\n' | sort`
- `find . -maxdepth 1 -mindepth 1 -not -path './.git' -exec du -sh {} \; | sort -h`
- `rg --files`
- `rg -n "if __name__ == ...|argparse|DataLoader|Dataset|MatrixCity|COLMAP|checkpoint|ckpt|eval" src scripts tools legacy`
- `git ls-files`, `git ls-files --others --exclude-standard`, and `git ls-files --others --ignored --exclude-standard`
- targeted `find` scans for `ckpt`, `checkpoints`, `tb`, `logs`, `run`, `runs`, `renders`, `assets`, `__pycache__`, `.pt`, `.ply`, `.npz`, `.log`, and notebooks

No notebooks were found with `find . -maxdepth 5 -type f -name '*.ipynb'`.

## Current Git State

- `git status --short --branch`: clean before creating this audit, on `fc/current-baseline-cleanup`.
- Tracked files: `668`.
- Untracked and not ignored before this audit: `0`.
- Ignored local files: `59127`.
- Tracked `results/` files: `434`.
- Tracked `data/` files: only `data/.gitkeep`.
- Total working tree size observed by `du`: about `194G`.

## Top-Level Directory Structure

| Path | Size | Classification | Notes |
| --- | ---: | --- | --- |
| `.claude/` | `8.0K` | generated_artifact | Local Claude settings are ignored. |
| `.dockerignore` | `4.0K` | keep | Docker build hygiene. |
| `.gitignore` | `8.0K` | keep | Already encodes most retention policy for data, results, checkpoints, TensorBoard, PLY/NPZ/log outputs, and viewer assets. |
| `CLAUDE.md` | `12K` | keep | Project guidance and mechanism notes. |
| `Dockerfile` | `4.0K` | keep | CUDA 12.1 / Python 3.11 / gsplat environment definition. |
| `docker-compose.yml` | `4.0K` | keep | Container entrypoint support. |
| `requirements.txt` | `4.0K` | keep | Python dependency reference. |
| `configs/` | `156K` | keep | Reproducible YAML experiment configs, including active FC-S5/S6/S6D families. |
| `data/` | `162G` | generated_artifact | Local datasets and caches; ignored except `data/.gitkeep`. |
| `docs/` | `308K` | keep | Research context, status, and experiment specs. |
| `external/` | `4.0K` | archive | Currently empty; `.gitignore` reserves `external/val3dity/` as local checkout/build artifact. |
| `legacy/` | `280K` | archive | PlanarSplat reference code. Useful for formula lineage, not active implementation surface. |
| `results/` | `24G` | keep | Mixed: curated reports/tables are keep; raw runs/checkpoints/logs under it are generated_artifact. |
| `scripts/` | `8.3M` | refactor | Many experiment runners, diagnostics, exports, and report generators. Reusable but needs entrypoint inventory before GS-JSO changes. |
| `src/` | `2.1M` | keep | Main source for Stage 2 training/loss/rendering and Stage 3 readout/export. |
| `tools/` | `1.5G` | refactor | Browser viewers and generated viewer assets. Static viewer code is useful; assets are generated_artifact. |

## Existing Training Entry Points

| Entry point | Classification | Purpose / assumptions |
| --- | --- | --- |
| `python -m src.stage2.train --config <yaml>` | keep | Main Stage 2 2DGS trainer. Reads YAML, creates `out_dir/ckpt`, `out_dir/renders`, `out_dir/tb`, and writes final checkpoint. |
| `scripts/phase2_synthesis/run_ablation.sh` | refactor | Launch helper for Phase 2 ablations. Shell runner, likely historical and environment-specific. |
| `scripts/phase2_synthesis/resume_both.sh` | refactor | Ad-hoc resume helper. Keep until superseded by documented runner. |
| `scripts/phase2_synthesis/run_post_training.sh` | refactor | Post-training pipeline helper. Needs argument/contract audit before reuse. |
| `scripts/phase2_synthesis/fc_s6d2_directional_screening.py` | keep | Current FC-S6D-2 artifact setup/report script. Explicitly says it does not modify Stage 3, Metric-v1, L_structure, G2, or Lmu7. |
| `scripts/phase2_synthesis/fc_s6d_directionality_setup.py` | keep | No-training directionality inventory and gradient-scale audit scaffold. |
| `scripts/phase2_synthesis/fc_s6e_joint_screening.py` | keep | Current joint screening artifact path for FC-S6E. |
| `legacy/planarsplat_ref/trainer.py` | archive | Legacy PlanarSplat trainer reference. Not active GS-JSO training path. |

Important current config facts:

- Active FC configs use `data_root: results/phase2_synthesis/dataset`.
- `configs/fc_s6/A8_no_terrain_terms.yaml` is the current A8 terrain-off reference.
- `configs/fc_s6d/A8_v2_geo.yaml` changes `mutual_mode` to `sem2geo` and writes to `results/FC_S6D_lmutual_directionality/phase2_screening/runs/A8_v2_geo`.
- `configs/fc_s6d/A8_v2_joint_BLOCKED.yaml` is explicitly blocked in config metadata.
- Current FC configs are long runs (`max_iter: 12000`), so they were not executed during this audit.

## Existing Evaluation / Export Entry Points

| Entry point | Classification | Purpose / outputs |
| --- | --- | --- |
| `scripts/stage2/eval_rendering.py` | keep | PSNR/SSIM/LPIPS rendering evaluation from checkpoint and config. |
| `scripts/stage2/eval_semantic.py` | keep | Renders semantic logits and computes mIoU/per-class IoU. |
| `scripts/stage2/eval_geometry.py` | keep | Compares Gaussian centers to GT PLY point cloud with Chamfer/F1 and optional ICP. |
| `scripts/stage2/eval_structure.py` | keep | Structure/grouping evaluation path. |
| `scripts/stage2/export_2dgs_ksplat.py`, `export_2dgs_surfels.py`, `export_ply*.py` | keep | Viewer/export utilities. Outputs are generated_artifact. |
| `scripts/phase2_synthesis/run_stage3.py` | keep | Stage 3 readout runner. |
| `scripts/phase2_synthesis/eval_citygml.py` | keep | CityJSON/CityGML quality evaluation summary writer. |
| `scripts/phase2_synthesis/fc_s6_collect_results.py` | keep | Aggregates FC-S6 metrics and writes curated reports/tables. |
| `tools/experiments/build_dashboard.py` | refactor | Builds browser dashboards and exports `.ksplat` assets. Useful but mixes build and artifact generation. |
| `tools/gs3d_4way_viewer/serve.py` | keep | Lightweight local static viewer server. |

## Dataset Loaders and Data Assumptions

Primary loader: `src/stage2/dataloader.py::ColmapDataset`.

Assumed dataset layout:

```text
root/
  images/
  sparse/0/
    cameras.bin
    images.bin
    points3D.bin
  stereo/depth_maps/      optional COLMAP PatchMatch depth
  stereo/normal_maps/     optional COLMAP PatchMatch normals
  depth/                  optional MatrixCity EXR depth
  normal/                 optional MatrixCity EXR normals
  semantic/               optional PNG semantic labels
```

Observed assumptions:

- COLMAP sparse binary files are required for cameras, images, and initial point cloud.
- Images are sorted by file name after COLMAP image loading.
- Depth/normal GT is auto-detected from either COLMAP `*.geometric.bin` / `*.photometric.bin` or MatrixCity-style EXR.
- MatrixCity EXR normals are decoded from BGR to RGB and from `(n+1)/2` to world-frame unit normals.
- COLMAP PatchMatch normals are converted camera-frame to world-frame.
- Semantic labels are PNGs under `semantic/`, classes are `0=BG`, `1=Roof`, `2=Wall`, `3=Terrain`.
- Current FC configs use `results/phase2_synthesis/gravity.json` for `e_gravity`.
- Stage 2 train/test split is deterministic by index: every 10th frame where `i % 10 == 9` is test.

Local data inventory:

| Path | Size | Classification | Notes |
| --- | ---: | --- | --- |
| `data/matrixcity/` | `162G` | generated_artifact | Local MatrixCity data, ignored. Includes images, sparse COLMAP, EXR blocks, point clouds, semantic labels, and HuggingFace cache metadata. |
| `data/matrixcity/images/` | `21G` | generated_artifact | RGB image payloads. |
| `data/matrixcity/sparse/` | `1.7G` | generated_artifact | COLMAP sparse data. |
| `data/matrixcity/small_city_pointcloud/` | `5.0G` | generated_artifact | PLY point-cloud GT used by geometry evaluation. |
| `data/matrixcity/small_city_depth_float32/` | `23G` | generated_artifact | MatrixCity depth payload. |
| `data/matrixcity/small_city_normal/` | `45G` | generated_artifact | MatrixCity normal payload. |
| `data/matrixcity/block_*_depth`, `block_*_normal` | `728M` to `13G` each | generated_artifact | Block-level EXR payloads. |
| `data/matrixcity/.cache/` | `148K` | remove_candidate | Local HuggingFace lock/metadata cache. Do not remove without user approval. |
| `data/3dbag/`, `data/seongsu/`, `data/synthetic/` | small placeholders here | generated_artifact | Data roots are ignored; only `data/.gitkeep` is tracked. |

## Existing Output, Checkpoint, and Cache Directories

The repository intentionally mixes tracked curated evidence with ignored local outputs. `.gitignore` already excludes most raw payload patterns.

| Path / pattern | Observed size or examples | Classification | Notes |
| --- | ---: | --- | --- |
| `results/phase1_*/run/ckpt/final.pt` | `826M` to `1.3G` each | generated_artifact | Local checkpoints, ignored by `*.pt` and run patterns. |
| `results/matrixcity_smoke/run/ckpt/final.pt` | `1.9G` | generated_artifact | Largest observed checkpoint. |
| `results/phase2_ablation_citygml/*/ckpt/*.pt` | about `229M` to `249M` each | generated_artifact | Multiple step checkpoints and final checkpoints. |
| `results/*/run/tb/`, `results/phase2_ablation_citygml/*/tb/` | TensorBoard event files up to `3.0M` each | generated_artifact | Ignored by policy. |
| `results/*/run/renders/`, `results/phase2_ablation_citygml/*/renders/` | not fully enumerated | generated_artifact | Render samples. |
| `results/stage3_rendered_evidence/` | `2.8G` | generated_artifact | Raw rendered evidence plus curated reports. Keep curated reports; ignore raw `.npz`, `.ply`, overlays. |
| `results/phase2_synthesis/dataset/` | `3.4G` | generated_artifact | Current FC training data root. Required for reruns but should not be committed. |
| `results/phase2_ablation_citygml/` | `6.0G` | keep | Mixed. Reports/figures/summaries are curated; `ckpt`, `tb`, `renders`, `stage3/primitives.npz` are generated_artifact. |
| `results/FC_*` | small curated files tracked; raw paths ignored | keep | Current FC reports, decision files, configs, and aggregate tables are curated evidence. Raw `logs`, `runs`, `checkpoints`, `evidence_exports`, `.log`, `.pid`, `.out`, `.npz`, `.ply` are generated_artifact. |
| `tools/gs3d_4way_viewer/assets/` | `1.1G` | generated_artifact | Ignored viewer assets, including `.ksplat` and surfels. |
| `tools/experiments/*/assets/` | hundreds of MB | generated_artifact | Ignored dashboard/viewer exports. |
| `tools/gs3d_4way_viewer/build/` | `9.3M`, tracked | refactor | Vendor/static JS bundle is tracked, including sourcemaps and demo bundle. |
| `__pycache__/` under `legacy`, `scripts`, `src` | present | remove_candidate | Python bytecode, ignored. |

Largest tracked files are curated figures or static bundles, not checkpoints. Examples:

- `results/phase1_depth_normal/figures/comparison_4views.png` around `34M`.
- `results/phase1_semantic/figures/comparison_4views.png` around `34M`.
- `results/phase1_mutual/figures/comparison_4views.png` around `34M`.
- `results/phase1_vanilla/figures/comparison_4views.png` around `33M`.
- `scripts/stage2/_sem_verify.png` around `2.9M`.
- `tools/gs3d_4way_viewer/build/*.map` around `0.9M` to `1.2M` each.

## Candidate Reusable Modules for GS-JSO

| Module / path | Classification | Reuse value |
| --- | --- | --- |
| `src/stage2/model.py` | keep | 2DGS primitive parameterization, SH colors, quaternions, normals, semantic logits. |
| `src/stage2/renderer.py` | keep | `gsplat.rasterization_2dgs` wrapper for RGB/depth/normals and semantic feature rendering. |
| `src/stage2/dataloader.py` | keep | COLMAP/MatrixCity data normalization and semantic/depth/normal loading. |
| `src/stage2/loss/data_fitting.py` | keep | Base photometric/depth/normal/semantic losses. |
| `src/stage2/loss/mutual.py` | keep | Active FC/GS-JSO mutual semantic-geometry prior surface. Supports `full`, `sem2geo`, and `geo2sem` directionality. |
| `src/stage2/loss/structure.py` | keep | Inter-primitive alignment/coplanarity objective, currently disabled in active FC policy. |
| `src/stage2/grouping.py` | refactor | G1/G2 grouping candidates and Stage 3 interface. Useful, but comments say G2 is target while current policy disallows enabling G2 without design review. |
| `src/stage2/densification.py` | keep | gsplat strategy/optimizer construction. |
| `src/stage2/colmap_io.py` | keep | COLMAP binary/text and dense array readers. |
| `src/stage3/*` | refactor | Stage 3 building readout, clustering, ground surface, convex polytope, CityJSON export. Useful, but likely needs clearer contracts for GS-JSO. |
| `scripts/phase2_synthesis/fc_s6*_*.py` | refactor | Report/evaluation generators encode experimental gates. Reuse after extracting stable library helpers. |
| `tools/gs3d_4way_viewer/` | refactor | Viewer is useful for QA; generated assets should stay ignored and regenerated. |

## Candidate Files / Directories to Archive or Ignore

| Path / pattern | Classification | Rationale |
| --- | --- | --- |
| `legacy/planarsplat_ref/` | archive | Reference formulas and historical implementation only. Keep read-only unless explicitly migrating logic. |
| `docs/archive/` | archive | Prior web brief versions. Keep as historical context. |
| `results/archive_seongsu_v0/` | archive | Historical Seongsu result tree with local run/checkpoint payloads. Curated `REPORT.md` can stay; raw run files are generated_artifact. |
| `results/phase1_*`, `results/phase2_*`, `results/stage3_*` | archive | Historical experiment evidence. Keep reports/summaries/selected figures; raw runs/checkpoints/evidence are generated_artifact. |
| `results/FC_S4_*`, `FC_S5_*`, `FC_S6*` curated reports/tables | keep | Current method lineage and decision evidence. |
| `results/FC_*/**/runs`, `checkpoints`, `logs`, `evidence_exports`, `viewer_screenshots` | generated_artifact | Already covered by `.gitignore`. Do not remove in this audit. |
| `tools/**/assets/` | generated_artifact | Viewer exports are ignored and regenerable. |
| `tools/gs3d_4way_viewer/build/demo/` and `*.map` | refactor | Tracked vendor/demo bundle and sourcemaps; consider vendor policy, not immediate deletion. |
| `scripts/stage2/_sem_verify.png` | remove_candidate | Image artifact living inside script directory. Confirm provenance before removal. |
| `__pycache__/`, `*.pyc` | remove_candidate | Python bytecode, ignored. Safe cleanup candidate after approval. |
| `data/matrixcity/.cache/` | remove_candidate | Local cache metadata and locks. Do not remove without approval because downloads are not being refreshed here. |

## Risks Before Cleanup

1. `results/` is not purely disposable. It contains the current FC method ledger, decision files, aggregate CSVs, reports, and selected figures. Broad deletion would destroy experiment provenance.
2. Local rerun capability depends on ignored data under `data/matrixcity/` and `results/phase2_synthesis/dataset/`. Cleanup must distinguish "not for git" from "safe to remove locally."
3. Active docs currently say A8 legacy terrain-off is the empirical reference. Cleanup should preserve `configs/fc_s6/A8_no_terrain_terms.yaml`, `configs/fc_s6d/A8_v2_geo.yaml`, `docs/experiments/FC_METHOD_CURRENT.md`, and FC-S6D/FC-S6E decision evidence.
4. Current FC configs target long training runs. Any implementation verification should use static checks or smoke configs unless the user explicitly asks for training.
5. `scripts/phase2_synthesis/` contains many one-off diagnostics with shared assumptions encoded as globals. Refactoring before preserving behavior can silently change reports.
6. `src/stage2/grouping.py` contains both G1 and G2. Current method policy says not to enable G2 as the main route without new review.
7. The viewer has tracked static JS bundles and ignored generated assets. Moving or ignoring the build bundle could break local QA pages unless replacement install/build steps are documented.
8. There is no detected notebook surface, so notebook cleanup is not needed now.

## Audit Conclusion

The repository is suitable for a GS-JSO implementation only after preserving the current FC baseline boundary:

- Keep source, configs, docs, current reports, aggregate tables, and viewer QA notes.
- Treat checkpoints, TensorBoard events, raw render/evidence payloads, `.pt`, `.ply`, `.npz`, `.ksplat`, local datasets, and viewer assets as generated artifacts.
- Refactor only around stable reusable modules and runner/report contracts; do not collapse historical result trees until the curated evidence set is explicitly approved.
