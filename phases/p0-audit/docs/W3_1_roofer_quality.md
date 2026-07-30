# W3-1 Roofer Roof Quality Metrics

- Run ID: `w3_1_roofer_quality_20260612_210850`
- Population: Roofer default both_success paired set, 67 buildings from `docs/W2_1c_paired_status.csv`.
- Reference: LoD2 CityGML `RoofSurface` polygons from `data/raw/lod2/*.gml`.
- Predictions: Roofer default ALS/DIM CityJSON from `runs/w2_1_roofer_default_20260612_152729/cityjson/`.
- Plane matching: XY projected roof polygons, one-to-one greedy matching, IoU >= 0.50.
- Boundary metrics: roof-union outline sampled every 0.50 m; symmetric Chamfer and Hausdorff in meters.
- Height metrics: matched roof intersection samples every 0.50 m; `pred_z - ref_z` median bias and NMAD spread.

## Median Summary

| metric | n | als_median | dim_median | dim_minus_als | dim_over_als | interpretation |
| --- | --- | --- | --- | --- | --- | --- |
| plane_f1 | 67 | 0.700000 | 0.571429 | -0.128571 | 0.816327 | higher_is_better |
| boundary_chamfer_m | 67 | 0.132148 | 0.143199 | 0.011051 | 1.083626 | lower_is_better |
| boundary_hausdorff_m | 67 | 0.190758 | 0.189572 | -0.001186 | 0.993783 | lower_is_better |
| height_bias_m | 63 | 0.013801 | -0.038490 | -0.052291 |  | signed_median_pred_minus_ref |
| height_nmad_m | 63 | 0.056373 | 0.080454 | 0.024081 | 1.427173 | lower_is_better |

## P0 Section 6 Threshold Position

| p0_section6_item | observed_value | threshold_value | observed_minus_threshold | definition |
| --- | --- | --- | --- | --- |
| plane_f1_drop | 0.128571 | 0.100000 | 0.028571 | ALS median plane_f1 - DIM median plane_f1 |
| boundary_chamfer_ratio | 1.083626 | 1.500000 | -0.416374 | DIM median boundary_chamfer_m / ALS median boundary_chamfer_m |
| boundary_hausdorff_ratio | 0.993783 | 1.500000 | -0.506217 | DIM median boundary_hausdorff_m / ALS median boundary_hausdorff_m |

## Figures

![Plane F1](../../../docs/evidence/p0_g1_20260613/figs/fig_04_plane_f1_boxplot.png)

![Boundary errors](../../../docs/evidence/p0_g1_20260613/figs/fig_05_boundary_error_boxplots.png)

![Height errors](../../../docs/evidence/p0_g1_20260613/figs/fig_06_height_error_boxplots.png)

## Files

- Building metrics: `docs/W3_1_roofer_quality_metrics.csv`
- Median summary: `docs/W3_1_roofer_quality_summary.csv`
- Threshold position table: `docs/W3_1_threshold_position.csv`

## W3-1b Addendum

- Matching spot-check overlays, internal boundary metrics, and the common height-bias outlier note are recorded in `docs/W3_1b_matching_validation.md`.
