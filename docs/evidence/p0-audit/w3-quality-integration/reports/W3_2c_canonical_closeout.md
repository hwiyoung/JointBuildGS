# W3-2c Canonical P0 Closeout

- Run ID: `w3_2c_canonical_closeout_20260612_222618`
- Canonical Roofer run: `w3_2b_roofer_repeatability_20260612_220747` `run_2`.
- Canonical harness: explicit Roofer defaults (`plane-detect-epsilon=0.30`, `plane-detect-min-points=15`, `complexity-factor=0.888`), `--jobs 32`, fixed AOI `--box`, and fixed 93-building `--filter`.
- Seed/log note: Roofer exposes no random seed in the CLI; W2-3a dev subset seed is 20260612. Canonical logs: `runs/w3_2b_roofer_repeatability_20260612_220747/logs/roofer_run_2_als_default.log` and `runs/w3_2b_roofer_repeatability_20260612_220747/logs/roofer_run_2_dim_default.log`.

## Canonical Success Rates

| population | n | als_success | dim_success | both_success | als_only | dim_only | both_fail | als_val3dity_valid | dim_val3dity_valid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_199 | 199 | 166/199 (83.4%) | 102/199 (51.3%) | 93/199 (46.7%) | 73/199 (36.7%) | 9/199 (4.5%) | 24/199 (12.1%) | 167/199 (83.9%) | 167/199 (83.9%) |
| both_attempted_179 | 179 | 166/179 (92.7%) | 102/179 (57.0%) | 93/179 (52.0%) | 73/179 (40.8%) | 9/179 (5.0%) | 4/179 (2.2%) | 167/179 (93.3%) | 167/179 (93.3%) |
| coverage_controlled_93 | 93 | 87/93 (93.5%) | 75/93 (80.6%) | 71/93 (76.3%) | 16/93 (17.2%) | 4/93 (4.3%) | 2/93 (2.2%) | 88/93 (94.6%) | 83/93 (89.2%) |

## Canonical Priority Buckets

| bucket | count | scope_note |
| --- | --- | --- |
| coverage | 85 | both attempted, outside W2-1c DIM coverage rule after reference-mismatch exclusions |
| aoi_edge | 20 | footprint centroid outside Roofer AOI box |
| reference_mismatch | 2 | 104586480 from W2-1c and 4906973 from W3-1b height-bias review |
| roof_matching | 8 | canonical DIM missing_lod22_geometry with coverage present |
| validity | 13 | coverage-control buildings with ALS or DIM validity bucket after roof-matching priority |
| remainder_after_priority | 71 | not assigned to non-success/exclusion buckets above; canonical quality table uses 71 paired both_success buildings |

## Canonical Quality Summary

| metric | n | als_median | dim_median | dim_minus_als | dim_over_als | interpretation |
| --- | --- | --- | --- | --- | --- | --- |
| plane_f1 | 71 | 0.666667 | 0.571429 | -0.095238 | 0.857143 | higher_is_better |
| boundary_chamfer_m | 71 | 0.126200 | 0.151802 | 0.025602 | 1.202868 | lower_is_better |
| boundary_hausdorff_m | 71 | 0.191575 | 0.191575 | 0.000000 | 1.000000 | lower_is_better |
| height_bias_m | 69 | 0.012943 | -0.039375 | -0.052318 |  | signed_median_pred_minus_ref |
| height_nmad_m | 69 | 0.059665 | 0.080237 | 0.020572 | 1.344792 | lower_is_better |
| internal_boundary_chamfer_m | 35 | 0.345675 | 0.377285 | 0.031610 | 1.091444 | matched roof-surface shared boundaries sampled at 0.50 m |
| internal_boundary_hausdorff_m | 35 | 1.470091 | 1.744066 | 0.273975 | 1.186366 | matched roof-surface shared boundaries sampled at 0.50 m |

## Quality Median Change

- Canonical 71-building medians are not uniformly within +/-0.02 of W3-1/W3-1b; max abs change is 0.056, outside entries: plane_f1:ALS, internal_boundary_chamfer_m:ALS, internal_boundary_chamfer_m:DIM, internal_boundary_hausdorff_m:ALS, internal_boundary_hausdorff_m:DIM. Exterior-boundary and height medians retain the previous numeric interpretation, while plane-F1/internal-boundary numeric text is replaced by canonical values.

| metric | input | old_n | canonical_n | old_median | canonical_median | canonical_minus_old | within_pm_0p02 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| plane_f1 | ALS | 67 | 71 | 0.700000 | 0.666667 | -0.033333 | no |
| plane_f1 | DIM | 67 | 71 | 0.571429 | 0.571429 | 0.000000 | yes |
| boundary_chamfer_m | ALS | 67 | 71 | 0.132148 | 0.126200 | -0.005948 | yes |
| boundary_chamfer_m | DIM | 67 | 71 | 0.143199 | 0.151802 | 0.008603 | yes |
| boundary_hausdorff_m | ALS | 67 | 71 | 0.190758 | 0.191575 | 0.000817 | yes |
| boundary_hausdorff_m | DIM | 67 | 71 | 0.189572 | 0.191575 | 0.002003 | yes |
| height_bias_m | ALS | 63 | 69 | 0.013801 | 0.012943 | -0.000858 | yes |
| height_bias_m | DIM | 63 | 69 | -0.038490 | -0.039375 | -0.000885 | yes |
| height_nmad_m | ALS | 63 | 69 | 0.056373 | 0.059665 | 0.003292 | yes |
| height_nmad_m | DIM | 63 | 69 | 0.080454 | 0.080237 | -0.000217 | yes |
| internal_boundary_chamfer_m | ALS | 36 | 35 | 0.396221 | 0.345675 | -0.050546 | no |
| internal_boundary_chamfer_m | DIM | 36 | 35 | 0.414909 | 0.377285 | -0.037624 | no |
| internal_boundary_hausdorff_m | ALS | 36 | 35 | 1.439189 | 1.470091 | 0.030902 | no |
| internal_boundary_hausdorff_m | DIM | 36 | 35 | 1.800416 | 1.744066 | -0.056350 | no |

## Section 6 Threshold Position

| item | observed_value | threshold_value | observed_minus_threshold | definition |
| --- | --- | --- | --- | --- |
| plane_f1_drop | 0.095238 | 0.100000 | -0.004762 | ALS median plane F1 minus DIM median plane F1 |
| exterior_boundary_chamfer_ratio | 1.202868 | 1.500000 | -0.297132 | DIM median exterior Chamfer divided by ALS median exterior Chamfer |
| exterior_boundary_hausdorff_ratio | 1.000000 | 1.500000 | -0.500000 | DIM median exterior Hausdorff divided by ALS median exterior Hausdorff |
| validity_rate_drop_pp | 5.376344 | 10.000000 | -4.623656 | coverage-control val3dity-valid rate: ALS 88/93 (94.6%) minus DIM 83/93 (89.2%) |

## Figure Update

- Figure 1.1a replacement: `docs/figs/w3_2c_dim_unrecovered_missing_lod22_DEBY_LOD2_4907182.png`.
- `DEBY_LOD2_4907510` remains documented as a preprocessing-recovered case via `docs/W2_3b_roof_matching_recovery.csv`.

## Files

- Canonical paired status: `docs/W3_2c_canonical_paired_status.csv`
- Canonical success rates: `docs/W3_2c_canonical_success_rates.csv`
- Canonical threshold table: `docs/W3_2c_canonical_threshold_position.csv`
- Canonical quality metrics: `docs/W3_2c_canonical_roofer_quality_metrics.csv`
- Quality median change: `docs/W3_2c_quality_median_change.csv`
