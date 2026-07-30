# W2-3b DIM Variant Tests

- Run ID: `w2_3b_dim_variants_20260612_205412`
- Baseline: W2-1c coverage-control 93 buildings from `docs/W2_1c_paired_status.csv`.
- Roofer parameters: defaults; plumbing kept fixed (`--id-attribute`, AOI `--box`, `--filter`, `--jobs 32`).
- H-wall variant: remove points with estimated vertical-plane normals (`abs(NormalZ) < 0.3`).
- H-density variant: PDAL `filters.sample(radius=0.3)` to reduce DIM density toward ALS-scale sampling.
- Baseline roof-matching/assembly failures tracked below are the 7 W2-1c DIM `roof_matching_assembly_failure` buildings.

## Variant Point Clouds

| variant | path | method | point_count | base_aoi_point_count | kept_fraction | removed_fraction | aoi_planimetric_density_pts_m2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| base_aoi_crop | data/work/w2_3b/dim_aoi_crop.laz | AOI crop before variant filtering | 43480044 | 43480044 | 1.000000 | 0.000000 | 244.609 |
| wall_removed | data/work/w2_3b/dim_wall_removed_nzge0p3.laz | PDAL crop -> filters.normal(knn=16, always_up=true) -> filters.expression(abs(NormalZ) >= 0.3) | 32391061 | 43480044 | 0.744964 | 0.255036 | 182.225 |
| thinned | data/work/w2_3b/dim_thinned_sample_r0p30.laz | PDAL crop -> filters.sample(radius=0.3) | 2555951 | 43480044 | 0.058784 | 0.941216 | 14.379 |

## Roofer Success vs Baseline DIM

| population | variant | n | baseline_dim_success | variant_dim_success | delta_dim_success_count | delta_dim_success_pp | baseline_both_success | variant_both_success | delta_both_success_count | delta_both_success_pp | baseline_roof_matching_failures | variant_roof_matching_failures | roof_matching_recovered_to_success |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| coverage_control_93_all | wall_removed | 93 | 75/93 (80.6%) | 73/93 (78.5%) | -2 | -2.2 | 67/93 (72.0%) | 66/93 (71.0%) | -1 | -1.1 | 7 | 8 | 1 |
| coverage_control_93_all | thinned | 93 | 75/93 (80.6%) | 72/93 (77.4%) | -3 | -3.2 | 67/93 (72.0%) | 67/93 (72.0%) | 0 | +0.0 | 7 | 7 | 1 |

## Roofer Density Summary

| variant | n_with_density | mean_rf_pt_density | median_rf_pt_density | min_rf_pt_density | max_rf_pt_density | target_density_note |
| --- | --- | --- | --- | --- | --- | --- |
| wall_removed | 93 | 308.863 | 212.714 | 36.429 | 1228.415 | ~21 pts/m2 for thinned; wall_removed has no density target |
| thinned | 93 | 19.147 | 16.615 | 7.806 | 151.811 | ~21 pts/m2 for thinned; wall_removed has no density target |

## Observations

- H-wall: wall_removed changed DIM success 75/93 (80.6%) -> 73/93 (78.5%) (delta -2, -2.2 pp) and recovered 1 of 7 baseline roof-matching failures.
- H-density: thinned reached mean Roofer footprint density 19.147 pts/m2 (target about 21 pts/m2), changed DIM success 75/93 (80.6%) -> 72/93 (77.4%) (delta -3, -3.2 pp), and recovered 1 of 7 baseline roof-matching failures.

## Failure Buckets

| population | variant | bucket_v1 | baseline_count | variant_count |
| --- | --- | --- | --- | --- |
| coverage_control_93_all | wall_removed | success | 75 | 73 |
| coverage_control_93_all | wall_removed | roof_matching_assembly_failure | 7 | 8 |
| coverage_control_93_all | wall_removed | validity | 11 | 12 |
| coverage_control_93_all | thinned | success | 75 | 72 |
| coverage_control_93_all | thinned | coverage | 0 | 1 |
| coverage_control_93_all | thinned | roof_matching_assembly_failure | 7 | 7 |
| coverage_control_93_all | thinned | validity | 11 | 13 |

## Roof-Matching Failure Recovery

- wall_removed recovered 1 of 7 baseline roof-matching failures.
- thinned recovered 1 of 7 baseline roof-matching failures.

| building_id | subset | variant | baseline_dim_status | baseline_dim_reason | variant_status | variant_reason | variant_bucket_v1 | recovered_to_success | variant_has_lod22 | variant_val3dity_valid | variant_rf_pt_density | variant_rf_nodata_frac | variant_rf_rmse_lod22 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DEBY_LOD2_42364609 | dev | wall_removed | failure | missing_lod22_geometry | failure | missing_lod22_geometry | roof_matching_assembly_failure | no | False | True | 36.428570 | 0.164179 | 0.000000 |
| DEBY_LOD2_42364609 | dev | thinned | failure | missing_lod22_geometry | failure | missing_lod22_geometry | roof_matching_assembly_failure | no | False | True | 8.145454 | 0.179104 | 0.000000 |
| DEBY_LOD2_42364659 | eval | wall_removed | failure | missing_lod22_geometry | failure | missing_lod22_geometry | roof_matching_assembly_failure | no | False | True | 87.954544 | 0.000000 | 0.000000 |
| DEBY_LOD2_42364659 | eval | thinned | failure | missing_lod22_geometry | failure | missing_lod22_geometry | roof_matching_assembly_failure | no | False | True | 13.924242 | 0.000000 | 0.000000 |
| DEBY_LOD2_4907182 | dev | wall_removed | failure | missing_lod22_geometry | failure | missing_lod22_geometry | roof_matching_assembly_failure | no | False | True | 50.358974 | 0.178947 | 0.000000 |
| DEBY_LOD2_4907182 | dev | thinned | failure | missing_lod22_geometry | failure | missing_lod22_geometry | roof_matching_assembly_failure | no | False | True | 9.437908 | 0.194737 | 0.000000 |
| DEBY_LOD2_4907510 | eval | wall_removed | failure | missing_lod22_geometry | success | success | success | yes | True | True | 42.160000 | 0.164927 | 4.454366 |
| DEBY_LOD2_4907510 | eval | thinned | failure | missing_lod22_geometry | success | success | success | yes | True | True | 13.089974 | 0.187891 | 6.273996 |
| DEBY_LOD2_4908050 | eval | wall_removed | failure | missing_lod22_geometry | failure | missing_lod22_geometry | roof_matching_assembly_failure | no | False | True | 37.527779 | 0.181818 | 0.000000 |
| DEBY_LOD2_4908050 | eval | thinned | failure | missing_lod22_geometry | failure | pointcloud_unusable_no_planes | coverage | no | False | True | 8.655738 | 0.191288 |  |
| DEBY_LOD2_4908166 | eval | wall_removed | failure | missing_lod22_geometry | failure | missing_lod22_geometry | roof_matching_assembly_failure | no | False | True | 39.096775 | 0.211864 | 0.000000 |
| DEBY_LOD2_4908166 | eval | thinned | failure | missing_lod22_geometry | failure | missing_lod22_geometry | roof_matching_assembly_failure | no | False | True | 8.602151 | 0.211864 | 0.000000 |
| DEBY_LOD2_4908176 | eval | wall_removed | failure | missing_lod22_geometry | failure | missing_lod22_geometry | roof_matching_assembly_failure | no | False | True | 36.551723 | 0.188811 | 0.000000 |
| DEBY_LOD2_4908176 | eval | thinned | failure | missing_lod22_geometry | failure | missing_lod22_geometry | roof_matching_assembly_failure | no | False | True | 8.666667 | 0.202797 | 0.000000 |

## Files

- Per-building variant status: `docs/W2_3b_variant_status.csv`
- Success summary: `docs/W2_3b_variant_success.csv`
- Bucket summary: `docs/W2_3b_bucket_summary.csv`
- 7-building recovery table: `docs/W2_3b_roof_matching_recovery.csv`
- Point-cloud variant stats: `docs/W2_3b_variant_pointcloud_stats.csv`
- Density summary: `docs/W2_3b_variant_density_summary.csv`
