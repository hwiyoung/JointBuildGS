# W3 P0 Integrated Summary

## Scope

- Canonical P0 closeout harness: W3-2b `run_2` with explicit Roofer defaults, fixed 93-building coverage-control filter, `--jobs 32`, and fixed AOI `--box`.
- Canonical logs: `runs/w3_2b_roofer_repeatability_20260612_220747/logs/roofer_run_2_als_default.log`, `runs/w3_2b_roofer_repeatability_20260612_220747/logs/roofer_run_2_dim_default.log`, and `runs/w3_2b_roofer_repeatability_20260612_220747/versions.txt`.
- Seed note: Roofer exposes no random seed in the CLI; W2-3a dev subset seed is 20260612.
- Main quality population: canonical coverage-control Roofer default paired `both_success` set, 71 buildings.

## Population Completeness

| population | n | als_success | dim_success | both_success | als_only | dim_only | both_fail | als_val3dity_valid | dim_val3dity_valid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_199 | 199 | 166/199 (83.4%) | 102/199 (51.3%) | 93/199 (46.7%) | 73/199 (36.7%) | 9/199 (4.5%) | 24/199 (12.1%) | 167/199 (83.9%) | 167/199 (83.9%) |
| both_attempted_179 | 179 | 166/179 (92.7%) | 102/179 (57.0%) | 93/179 (52.0%) | 73/179 (40.8%) | 9/179 (5.0%) | 4/179 (2.2%) | 167/179 (93.3%) | 167/179 (93.3%) |
| coverage_controlled_93 | 93 | 87/93 (93.5%) | 75/93 (80.6%) | 71/93 (76.3%) | 16/93 (17.2%) | 4/93 (4.3%) | 2/93 (2.2%) | 88/93 (94.6%) | 83/93 (89.2%) |

## Final Building-Level Buckets

One priority bucket is assigned per building for the 199-building accounting: AOI edge first, then reference mismatch, then coverage-control miss, then roof matching/assembly, then validity.

| bucket | count | scope_note |
| --- | --- | --- |
| coverage | 85 | both attempted, outside W2-1c DIM coverage rule after reference-mismatch exclusions |
| aoi_edge | 20 | footprint centroid outside Roofer AOI box |
| reference_mismatch | 2 | 104586480 from W2-1c and 4906973 from W3-1b height-bias review |
| roof_matching | 8 | canonical DIM missing_lod22_geometry with coverage present |
| validity | 13 | coverage-control buildings with ALS or DIM validity bucket after roof-matching priority |
| remainder_after_priority | 71 | not assigned to non-success/exclusion buckets above; canonical quality table uses 71 paired both_success buildings |

Input-level bucket counts are recorded in `docs/W3_2c_canonical_input_bucket_summary.csv`.

## Quality Metrics

Medians are paired by building where the metric is finite.

| metric | n | ALS median | DIM median | DIM minus ALS | DIM over ALS | note |
| --- | --- | --- | --- | --- | --- | --- |
| plane F1 | 71 | 0.666667 | 0.571429 | -0.095238 | 0.857143 | projected roof-surface IoU >= 0.50 matching |
| exterior boundary Chamfer (m) | 71 | 0.126200 | 0.151802 | 0.025602 | 1.202868 | roof-union outline, footprint-sensitive |
| exterior boundary Hausdorff (m) | 71 | 0.191575 | 0.191575 | 0.000000 | 1.000000 | roof-union outline, footprint-sensitive |
| internal boundary Chamfer (m) | 35 | 0.345675 | 0.377285 | 0.031610 | 1.091444 | matched roof-surface shared boundaries |
| internal boundary Hausdorff (m) | 35 | 1.470091 | 1.744066 | 0.273975 | 1.186366 | matched roof-surface shared boundaries |
| height bias (m) | 69 | 0.012943 | -0.039375 | -0.052318 |  | signed median `pred_z - ref_z` |
| height NMAD (m) | 69 | 0.059665 | 0.080237 | 0.020572 | 1.344792 | matched roof-intersection samples |

## Robustness Checks

| check | population | result summary | delta note |
| --- | --- | --- | --- |
| W2-3a Roofer grid, ALS | dev15; applied to 93 | selected `default` (`epsilon=0.3`, `min_points=15`, `complexity=0.888`) | canonical run_2 ALS success is 87/93 (93.5%); the pre-canonical W2-3a selected-default rerun also recorded 87/93 |
| W2-3a Roofer grid, DIM | dev15; applied to 93 | selected `default` (`epsilon=0.3`, `min_points=15`, `complexity=0.888`) | canonical run_2 DIM success is 75/93 (80.6%) and paired both success is 71/93 (76.3%); pre-canonical selected-default rows were 76/93 and 72/93 |
| W2-3b wall_removed | coverage-control 93 | remove points with `abs(NormalZ) < 0.3` | vs canonical run_2: DIM success 75/93 -> 73/93 (-2.2 pp); paired both success 71/93 -> 66/93 (-5.4 pp); original 7-case roof-matching trace recovered 1/7 |
| W2-3b thinned | coverage-control 93 | PDAL sample radius 0.3; mean Roofer footprint density 19.147 pts/m2 | vs canonical run_2: DIM success 75/93 -> 72/93 (-3.2 pp); paired both success 71/93 -> 67/93 (-4.3 pp); original 7-case roof-matching trace recovered 1/7 |
| W3-2b repeatability | canonical 93 | three same-settings explicit-default runs | run noise +/-0.5 pp by half-range; unstable building `DEBY_LOD2_60042` |
| City3D scope note | coverage-control 93 | W2-2 default comparison recorded City3D success 1/93 for ALS and 1/93 for DIM | W2-2b retained City3D as a scoped comparison artifact rather than extending the P0 Roofer quality analysis |

Quality stability note: Canonical 71-building medians are not uniformly within +/-0.02 of W3-1/W3-1b; max abs change is 0.056, outside entries: plane_f1:ALS, internal_boundary_chamfer_m:ALS, internal_boundary_chamfer_m:DIM, internal_boundary_hausdorff_m:ALS, internal_boundary_hausdorff_m:DIM. Exterior-boundary and height medians retain the previous numeric interpretation, while plane-F1/internal-boundary numeric text is replaced by canonical values.

### Roof-Matching Recovery Trace

| building_id | subset | wall_removed | thinned |
| --- | --- | --- | --- |
| DEBY_LOD2_42364609 | dev | no recovery | no recovery |
| DEBY_LOD2_42364659 | eval | no recovery | no recovery |
| DEBY_LOD2_4907182 | dev | no recovery | no recovery |
| DEBY_LOD2_4907510 | eval | recovered | recovered |
| DEBY_LOD2_4908050 | eval | no recovery | no recovery |
| DEBY_LOD2_4908166 | eval | no recovery | no recovery |
| DEBY_LOD2_4908176 | eval | no recovery | no recovery |

Body case note: `DEBY_LOD2_4907510` is now used as the preprocessing-recovered type, not Figure 1.1a.

## Section 6 Threshold Position

| item | observed_value | threshold_value | observed_minus_threshold | definition |
| --- | --- | --- | --- | --- |
| plane_f1_drop | 0.095238 | 0.100000 | -0.004762 | ALS median plane F1 minus DIM median plane F1 |
| exterior_boundary_chamfer_ratio | 1.202868 | 1.500000 | -0.297132 | DIM median exterior Chamfer divided by ALS median exterior Chamfer |
| exterior_boundary_hausdorff_ratio | 1.000000 | 1.500000 | -0.500000 | DIM median exterior Hausdorff divided by ALS median exterior Hausdorff |
| validity_rate_drop_pp | 5.376344 | 10.000000 | -4.623656 | coverage-control val3dity-valid rate: ALS 88/93 (94.6%) minus DIM 83/93 (89.2%) |

## Interpretation Notes

- Plane F1 reflects reference granularity as well as reconstruction behavior: LoD2 reference roof surfaces can split one visually continuous roof into more instances than Roofer predicts, so F1 is sensitive to plane-instance granularity.
- Exterior boundary error is damped by the footprint prior: Roofer preserves the planimetric building outline closely, so exterior Chamfer/Hausdorff are less input-sensitive than roof-plane F1 or internal shared boundaries.
- `validity != correctness`: `DEBY_LOD2_104586480` shows a ghost-slab case where ALS produced a flat geometry over an effectively empty footprint interior while the model was still val3dity-valid.

## Limitations

- Single-scene evidence: all numbers come from the same AOI and footprint set.
- City3D scope: City3D results are retained as W2 comparison context, while W3 quality tables focus on Roofer.
- Roofer grid size: W2-3a used a small, predeclared grid over three parameters.
- Input date gap: ALS is 2022-era data, while UAV image filenames indicate 2024-12-17; the modality timestamp gap is about 2.8 years.
- Dev15 split: the W2-3a dev subset is reported separately and remains marked in downstream robustness tables.
- Harness alignment: W3-2c canonicalizes the explicit-default 93-building harness at W3-2b `run_2`; earlier W2-1c/W3-1 tables remain provenance records for the pre-canonical baseline.

## Figure List

| figure | content | file |
| --- | --- | --- |
| Figure 1.1a | `DEBY_LOD2_4907182` canonical DIM roof-matching/assembly case that did not recover under wall removal or thinning | docs/figs/w3_2c_dim_unrecovered_missing_lod22_DEBY_LOD2_4907182.png |
| Figure 1.1b | `DEBY_LOD2_4907518` matched roof planes and ridge/shared-boundary comparison spot check | docs/figs/w3_1b_matching_overlay_mid_DEBY_LOD2_4907518.png |
| Figure 1.2 | canonical W3-2c plane F1 table source | docs/W3_2c_canonical_roofer_quality_summary.csv |
| Figure 1.3 | canonical W3-2c exterior/internal boundary table source | docs/W3_2c_canonical_internal_boundary_summary.csv |
| Figure 1.4 | canonical W3-2c height-error table source | docs/W3_2c_canonical_roofer_quality_summary.csv |

## Source Tables

- `docs/W3_2c_canonical_success_rates.csv`
- `docs/W3_2c_canonical_priority_buckets.csv`
- `docs/W3_2c_canonical_input_bucket_summary.csv`
- `docs/W3_2c_canonical_roofer_quality_summary.csv`
- `docs/W3_2c_canonical_internal_boundary_summary.csv`
- `docs/W3_2c_canonical_threshold_position.csv`
- `docs/W3_2c_quality_median_change.csv`
- `docs/W3_2b_roofer_repeatability_success.csv`
- `docs/W2_3b_roof_matching_recovery.csv`
