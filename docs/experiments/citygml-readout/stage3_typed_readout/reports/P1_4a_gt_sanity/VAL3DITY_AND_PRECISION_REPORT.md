# P1-4a Preflight: val3dity + Precision Metrics

## Scope

Target artifacts: `relation_readout.city.json`, `metrics.json`, GT mesh from `results/phase2_synthesis/scene.obj`, and per-building stepwise JSON files under `results/stage3_typed_readout/P1_4a_gt_sanity`.

Distance metrics use 6000 area-weighted predicted surface samples and 6000 area-weighted GT mesh samples. Recall coverage and pred-to-GT precision use a 0.5m threshold.

Footprint IoU is predicted `GroundSurface` projected to x/z against the GT `Ground` footprint projected to x/z. `selected_footprint_area_ratio` is the selected wall-derived footprint area divided by GT footprint area.

## val3dity Preflight

- Binary: `MISSING`
- Missing-path reason: no executable named `val3dity` was found on `PATH` or common local install directories.
- Search paths checked:
  - `/home/innopam/.codex/tmp/arg0/codex-arg09brqrZ/val3dity`
  - `/home/innopam/.vscode-server/cli/servers/Stable-cfbea10c5ffb233ea9177d34726e6056e89913dc/server/bin/remote-cli/val3dity`
  - `/usr/local/cuda-11.8/bin/val3dity`
  - `/home/innopam/miniconda3/bin/val3dity`
  - `/home/innopam/miniconda3/condabin/val3dity`
  - `/usr/local/sbin/val3dity`
  - `/usr/local/bin/val3dity`
  - `/usr/sbin/val3dity`
  - `/usr/bin/val3dity`
  - `/sbin/val3dity`
  - `/bin/val3dity`
  - `/usr/games/val3dity`
  - `/usr/local/games/val3dity`
  - `/snap/bin/val3dity`
  - `/home/innopam/.vscode-server/extensions/openai.chatgpt-26.422.71525-linux-x64/bin/linux-x86_64/val3dity`
  - `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS/bin/val3dity`
  - `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS/tools/val3dity`
  - `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS/external/val3dity`
  - `/home/innopam/.local/bin/val3dity`
  - `/opt/conda/bin/val3dity`
- Installation note: on Linux, the official project currently expects a source build with CMake after installing CGAL/Eigen/GEOS/Boost dependencies.
- Official install docs: https://val3dity.readthedocs.io/main/install.html
- Official usage docs: https://val3dity.readthedocs.io/main/usage.html
- Source: https://github.com/tudelft3d/val3dity

## Table 1. Formal validity

| bid | val3dity | errors | edge_ok | face_planarity_max | open_edges | nonmanifold_edges |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | MISSING | val3dity_not_found | True | 0.000000 | 0 | 0 |
| B2 | MISSING | val3dity_not_found | True | 0.000000 | 0 | 0 |
| B8 | MISSING | val3dity_not_found | True | 0.000000 | 0 | 0 |
| B6 | MISSING | val3dity_not_found | True | 0.000000 | 0 | 0 |
| B0 | MISSING | val3dity_not_found | True | 0.000000 | 0 | 0 |
| B3 | MISSING | val3dity_not_found | True | 0.000000 | 0 | 0 |

## Table 2. Final geometry

| bid | h_err | recall_coverage | pred_precision | F_score | vol_ratio | footprint_IoU | Hausdorff | Chamfer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 0.0000 | 0.990 | 0.990 | 0.990 | 1.000 | 1.000 | 0.7375 | 0.2113 |
| B2 | 0.0000 | 1.000 | 0.999 | 0.999 | 1.620 | 0.997 | 0.6752 | 0.1671 |
| B8 | 0.0010 | 0.988 | 0.994 | 0.991 | 1.392 | 0.997 | 0.6726 | 0.1854 |
| B6 | 3.6070 | 0.883 | 0.931 | 0.907 | 0.630 | 0.992 | 3.9262 | 0.2859 |
| B0 | 0.0000 | 0.902 | 0.906 | 0.904 | 2.164 | 0.999 | 2.3981 | 0.2671 |
| B3 | 7.3050 | 0.365 | 0.320 | 0.341 | 0.956 | 0.970 | 11.4784 | 1.8713 |

Additional geometry fields written to each `metrics_preflight_precision.json`: `bbox_IoU`, `surface_area_ratio`, `n_edges`, `output_h`, `GT_h`, `output_vol`, `GT_vol`.

## Table 3. Stepwise summary

| bid | n_wall_nodes | n_roof_nodes | n_footprint_candidates | selected_footprint_area_ratio | n_roof_surfaces | optional_archetype | failure_hint |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 5 | 1 | 5 | 1.000 | 4 | flat-like | val3dity_missing |
| B2 | 5 | 1 | 5 | 1.003 | 5 | flat-like | val3dity_missing |
| B8 | 7 | 1 | 5 | 1.003 | 7 | flat-like | val3dity_missing |
| B6 | 16 | 4 | 5 | 1.009 | 12 | hip-like | val3dity_missing+height_error |
| B0 | 14 | 3 | 5 | 1.001 | 10 | gable-like | val3dity_missing |
| B3 | 48 | 22 | 3 | 1.031 | 11 | hip-like | val3dity_missing+height_error+recall_low+precision_low |

## Formal GO/NG update

- Overall formal decision: `BLOCKED_VAL3DITY_MISSING`.
- Simple/medium rule (B1/B2/B8/B0, need >=3 val3dity PASS and F_score > 0.6): `NOT_PASS`; hits: none.
- Hip branch rule (B6, need val3dity PASS and F_score > 0.5): `NOT_PASS`.
- Complex branch rule (B3 expected fail/separate): `SEPARATE_COMPLEX_BRANCH`.

Because val3dity is missing, the formal GO/NG remains blocked even where geometry-side F-score clears the threshold.
- Geometry-side simple/medium F_score > 0.6: 4/4 (B1, B2, B8, B0).
- Geometry-side B6 F_score > 0.5: yes (F_score=0.907).

## Self-verification

- PASS: every target bid has either a val3dity result or a missing-path reason in `val3dity_relation_preflight.json`.
- PASS: pred-to-GT precision, F-score, and footprint IoU were computed for every target bid.
- PASS: recall coverage and precision are both present in Table 2.
- PASS: formal GO/NG was updated; current state is blocked by missing validator when no binary is found.
