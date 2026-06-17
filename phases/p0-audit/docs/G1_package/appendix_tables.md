# G1 Appendix Tables

## Canonical Three-Level Completeness

| population | n | als_success | dim_success | both_success | als_only | dim_only | both_non_success | als_val3dity_valid | dim_val3dity_valid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full_199 | 199 | 166/199 (83.4%) | 102/199 (51.3%) | 93/199 (46.7%) | 73/199 (36.7%) | 9/199 (4.5%) | 24/199 (12.1%) | 167/199 (83.9%) | 167/199 (83.9%) |
| both_attempted_179 | 179 | 166/179 (92.7%) | 102/179 (57.0%) | 93/179 (52.0%) | 73/179 (40.8%) | 9/179 (5.0%) | 4/179 (2.2%) | 167/179 (93.3%) | 167/179 (93.3%) |
| coverage_controlled_93 | 93 | 87/93 (93.5%) | 75/93 (80.6%) | 71/93 (76.3%) | 16/93 (17.2%) | 4/93 (4.3%) | 2/93 (2.2%) | 88/93 (94.6%) | 83/93 (89.2%) |

## Priority Buckets

| bucket | count | scope_note |
| --- | --- | --- |
| coverage | 85 | both attempted, outside W2-1c DIM coverage rule after reference-mismatch exclusions |
| aoi_edge | 20 | footprint centroid outside Roofer AOI box |
| reference_mismatch | 2 | 104586480 from W2-1c and 4906973 from W3-1b height-bias review |
| roof_matching | 8 | canonical DIM missing_lod22_geometry with coverage present |
| validity | 13 | coverage-control buildings with ALS or DIM validity bucket after roof-matching priority |
| remainder_after_priority | 71 | not assigned to non-success/exclusion buckets above; canonical quality table uses 71 paired both_success buildings |

## Quality Metrics With n

| metric | n | ALS_median | DIM_median | DIM_minus_ALS | DIM_over_ALS | source |
| --- | --- | --- | --- | --- | --- | --- |
| plane_f1 | 71 | 0.666667 | 0.571429 | -0.095238 | 0.857143 | docs/W3_2c_canonical_roofer_quality_summary.csv |
| boundary_chamfer_m | 71 | 0.126200 | 0.151802 | 0.025602 | 1.202868 | docs/W3_2c_canonical_roofer_quality_summary.csv |
| boundary_hausdorff_m | 71 | 0.191575 | 0.191575 | 0.000000 | 1.000000 | docs/W3_2c_canonical_roofer_quality_summary.csv |
| height_bias_m | 69 | 0.012943 | -0.039375 | -0.052318 |  | docs/W3_2c_canonical_roofer_quality_summary.csv |
| height_nmad_m | 69 | 0.059665 | 0.080237 | 0.020572 | 1.344792 | docs/W3_2c_canonical_roofer_quality_summary.csv |
| internal_boundary_chamfer_m | 35 | 0.345675 | 0.377285 | 0.031610 | 1.091444 | docs/W3_2c_canonical_internal_boundary_summary.csv |
| internal_boundary_hausdorff_m | 35 | 1.470091 | 1.744066 | 0.273975 | 1.186366 | docs/W3_2c_canonical_internal_boundary_summary.csv |

## Robustness Summary

| check | population | baseline_or_anchor | variant_or_repeat | delta | source |
| --- | --- | --- | --- | --- | --- |
| W2-3a tuning ALS | coverage_control_93_all | 84/93 (90.3%) | 87/93 (93.5%) | 3 (+3.2 pp) | docs/W2_3a_paired_success.csv |
| W2-3a tuning DIM | coverage_control_93_all | 75/93 (80.6%) | 76/93 (81.7%) | 1 (+1.1 pp) | docs/W2_3a_paired_success.csv |
| W2-3a tuning PAIRED_BOTH_SUCCESS | coverage_control_93_all | 67/93 (72.0%) | 72/93 (77.4%) | 5 (+5.4 pp) | docs/W2_3a_paired_success.csv |
| W2-3b wall_removed DIM | coverage_control_93_all | 75/93 (80.6%) | 73/93 (78.5%) | -2 (-2.2 pp); missing_lod22 to success count 1 | docs/W2_3b_variant_success.csv |
| W2-3b thinned DIM | coverage_control_93_all | 75/93 (80.6%) | 72/93 (77.4%) | -3 (-3.2 pp); missing_lod22 to success count 1 | docs/W2_3b_variant_success.csv |
| W3-2b repeatability ALS | coverage_control_93 | 87;87;87 | 3 runs | half-range 0.000000 pp | docs/W3_2b_roofer_repeatability_noise.csv |
| W3-2b repeatability DIM | coverage_control_93 | 76;75;75 | 3 runs | half-range 0.537634 pp | docs/W3_2b_roofer_repeatability_noise.csv |
| W3-2b repeatability PAIRED_BOTH_SUCCESS | coverage_control_93 | 72;71;71 | 3 runs | half-range 0.537634 pp | docs/W3_2b_roofer_repeatability_noise.csv |

## Canonical Missing-LoD2.2 Variant Trace

| building_id | wall_removed | thinned | trace_note |
| --- | --- | --- | --- |
| DEBY_LOD2_42364609 | not recovered (missing_lod22_geometry) | not recovered (missing_lod22_geometry) | present in W2-3b trace |
| DEBY_LOD2_42364659 | not recovered (missing_lod22_geometry) | not recovered (missing_lod22_geometry) | present in W2-3b trace |
| DEBY_LOD2_42364663 | not traced | not traced | not in W2-3b 7-case trace; added by canonical run_2 |
| DEBY_LOD2_4907182 | not recovered (missing_lod22_geometry) | not recovered (missing_lod22_geometry) | present in W2-3b trace |
| DEBY_LOD2_4907510 | recovered (success) | recovered (success) | present in W2-3b trace |
| DEBY_LOD2_4908050 | not recovered (missing_lod22_geometry) | not recovered (pointcloud_unusable_no_planes) | present in W2-3b trace |
| DEBY_LOD2_4908166 | not recovered (missing_lod22_geometry) | not recovered (missing_lod22_geometry) | present in W2-3b trace |
| DEBY_LOD2_4908176 | not recovered (missing_lod22_geometry) | not recovered (missing_lod22_geometry) | present in W2-3b trace |

## Section 6 Threshold Position

| item | observed_value | threshold_value | observed_minus_threshold | definition |
| --- | --- | --- | --- | --- |
| plane_f1_drop | 0.095238 | 0.100000 | -0.004762 | ALS median plane F1 minus DIM median plane F1 |
| exterior_boundary_chamfer_ratio | 1.202868 | 1.500000 | -0.297132 | DIM median exterior Chamfer divided by ALS median exterior Chamfer |
| exterior_boundary_hausdorff_ratio | 1.000000 | 1.500000 | -0.500000 | DIM median exterior Hausdorff divided by ALS median exterior Hausdorff |
| validity_rate_drop_pp | 5.376344 | 10.000000 | -4.623656 | coverage-control val3dity-valid rate: ALS 88/93 (94.6%) minus DIM 83/93 (89.2%) |

## Old Harness To Canonical Harness Comparison

| item | old_harness | canonical | source |
| --- | --- | --- | --- |
| coverage-control paired both success | 67/93 (72.0%) | 71/93 (76.3%) | docs/W2_1c_success_rates.csv; docs/W3_2c_canonical_success_rates.csv |
| ALS final success | 84/93 (90.3%) | 87/93 (93.5%) | docs/W2_1c_success_rates.csv; docs/W3_2c_canonical_success_rates.csv |
| DIM final success | 75/93 (80.6%) | 75/93 (80.6%) | docs/W2_1c_success_rates.csv; docs/W3_2c_canonical_success_rates.csv |
| Plane F1 drop | 0.128571 | 0.095238 | docs/W3_1_threshold_position.csv; docs/W3_2c_canonical_threshold_position.csv |
| DIM roof-matching bucket | 7 | 8 | docs/W2_1c_failure_bucket_summary.csv; docs/W3_2c_canonical_input_bucket_summary.csv |
