# W3 P0 Integrated Summary

## Scope

- Pipeline focus: Roofer default paired comparison, W2-3 Roofer robustness checks, and W3 roof-quality metrics.
- Main quality population: W2-1c coverage-control Roofer default `both_success` set, 67 buildings.
- Coverage-control denominator remains the W2-1c set of 93 buildings. W3-1b adds `DEBY_LOD2_4906973` as a reference-mismatch candidate for quality interpretation, without retroactively changing the W3-1 metric denominator.

## Population Completeness

| population | n | ALS success | DIM success | both success | ALS only | DIM only | both fail |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full_199 | 199 | 163/199 (81.9%) | 102/199 (51.3%) | 89/199 (44.7%) | 74/199 (37.2%) | 13/199 (6.5%) | 23/199 (11.6%) |
| both_attempted_179 | 179 | 163/179 (91.1%) | 102/179 (57.0%) | 89/179 (49.7%) | 74/179 (41.3%) | 13/179 (7.3%) | 3/179 (1.7%) |
| coverage_controlled_93 | 93 | 84/93 (90.3%) | 75/93 (80.6%) | 67/93 (72.0%) | 17/93 (18.3%) | 8/93 (8.6%) | 1/93 (1.1%) |

## Final Building-Level Buckets

One priority bucket is assigned per building for the 199-building accounting: AOI edge first, then reference mismatch, then coverage-control miss, then roof matching/assembly, then validity. The remaining row is the W3 quality-metric population.

| bucket | count | scope note |
| --- | ---: | --- |
| coverage | 85 | both attempted, but outside W2-1c DIM coverage rule (`nodata_frac <= 0.3` and density `>= 20 pts/m2`) after the W2-1c reference-mismatch exclusion |
| aoi_edge | 20 | footprint centroid outside Roofer AOI box; separated from reference mismatch in W2-1d |
| reference_mismatch | 2 | `DEBY_LOD2_104586480` from W2-1c and `DEBY_LOD2_4906973` from W3-1b height-bias review |
| roof_matching | 7 | W2-1c DIM `missing_lod22_geometry` with coverage present |
| validity | 18 | coverage-control buildings with ALS or DIM validity bucket after roof-matching priority |
| remainder_after_priority | 67 | buildings not assigned to the non-success/exclusion buckets above in this priority accounting; W3-1 quality metrics separately use the 67 paired `both_success` buildings |

Input-level bucket counts remain in `docs/W2_1c_failure_bucket_summary.csv`.

## Quality Metrics

Medians are paired by building where the metric is finite.

| metric | n | ALS median | DIM median | DIM minus ALS | DIM over ALS | note |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| plane F1 | 67 | 0.700000 | 0.571429 | -0.128571 | 0.816327 | projected roof-surface IoU >= 0.50 matching |
| exterior boundary Chamfer (m) | 67 | 0.132148 | 0.143199 | 0.011051 | 1.083626 | roof-union outline, footprint-sensitive |
| exterior boundary Hausdorff (m) | 67 | 0.190758 | 0.189572 | -0.001186 | 0.993783 | roof-union outline, footprint-sensitive |
| internal boundary Chamfer (m) | 36 | 0.396221 | 0.414909 | 0.018688 | 1.047167 | matched roof-surface shared boundaries |
| internal boundary Hausdorff (m) | 36 | 1.439189 | 1.800416 | 0.361227 | 1.250993 | matched roof-surface shared boundaries |
| height bias (m) | 63 | 0.013801 | -0.038490 | -0.052291 |  | signed median `pred_z - ref_z` |
| height NMAD (m) | 63 | 0.056373 | 0.080454 | 0.024081 | 1.427173 | matched roof-intersection samples |

## Robustness Checks

| check | population | result summary | delta note |
| --- | --- | --- | --- |
| W2-3a Roofer grid, ALS | dev15; applied to 93 | selected `default` (`epsilon=0.3`, `min_points=15`, `complexity=0.888`) | selected-default rerun changed ALS success 84/93 -> 87/93 (+3.2 pp) |
| W2-3a Roofer grid, DIM | dev15; applied to 93 | selected `default` (`epsilon=0.3`, `min_points=15`, `complexity=0.888`) | selected-default rerun changed DIM success 75/93 -> 76/93 (+1.1 pp); paired both success 67/93 -> 72/93 (+5.4 pp) |
| W2-3b wall_removed | coverage-control 93 | remove points with `abs(NormalZ) < 0.3` | DIM success 75/93 -> 73/93 (-2.2 pp); paired both success 67/93 -> 66/93 (-1.1 pp); roof-matching recovery 1/7 |
| W2-3b thinned | coverage-control 93 | PDAL sample radius 0.3; mean Roofer footprint density 19.147 pts/m2 | DIM success 75/93 -> 72/93 (-3.2 pp); paired both success 67/93 -> 67/93 (+0.0 pp); roof-matching recovery 1/7 |
| City3D scope note | coverage-control 93 | W2-2 default comparison recorded City3D success 1/93 for ALS and 1/93 for DIM | W2-2b retained City3D as a scoped comparison artifact rather than extending the P0 Roofer quality analysis |

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

## Section 6 Threshold Position

| item | observed value | threshold value | observed minus threshold | definition |
| --- | ---: | ---: | ---: | --- |
| plane_f1_drop | 0.128571 | 0.100000 | 0.028571 | ALS median plane F1 minus DIM median plane F1 |
| exterior_boundary_chamfer_ratio | 1.083626 | 1.500000 | -0.416374 | DIM median exterior Chamfer divided by ALS median exterior Chamfer |
| exterior_boundary_hausdorff_ratio | 0.993783 | 1.500000 | -0.506217 | DIM median exterior Hausdorff divided by ALS median exterior Hausdorff |
| validity_rate_drop_pp | 3.225806 | 10.000000 | -6.774194 | coverage-control val3dity-valid rate: ALS 85/93 (91.4%) minus DIM 82/93 (88.2%) |

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

## Figure List

| figure | content | file |
| --- | --- | --- |
| Figure 1.1a | `DEBY_LOD2_4907510` DIM roof-matching/assembly case, baseline vs available context | `docs/figs/w2_1b_dim_missing_lod22_DEBY_LOD2_4907510.png` |
| Figure 1.1b | `DEBY_LOD2_4907518` matched roof planes and ridge/shared-boundary comparison spot check | `docs/figs/w3_1b_matching_overlay_mid_DEBY_LOD2_4907518.png` |
| Figure 1.2 | W3-1 plane F1 boxplot | `docs/figs/w3_1_plane_f1_boxplot.png` |
| Figure 1.3 | W3-1 exterior boundary boxplots | `docs/figs/w3_1_boundary_error_boxplots.png` |
| Figure 1.4 | W3-1 height error boxplots | `docs/figs/w3_1_height_error_boxplots.png` |

## Source Tables

- `docs/W2_1c_success_rates.csv`
- `docs/W2_1c_failure_bucket_summary.csv`
- `docs/W2_3a_selected_params.csv`
- `docs/W2_3a_paired_success.csv`
- `docs/W2_3b_variant_success.csv`
- `docs/W2_3b_roof_matching_recovery.csv`
- `docs/W3_1_roofer_quality_summary.csv`
- `docs/W3_1_threshold_position.csv`
- `docs/W3_1b_internal_boundary_summary.csv`
- `docs/W3_1b_height_outlier_note.csv`
