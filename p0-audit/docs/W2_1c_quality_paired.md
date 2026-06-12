# W2-1c Quality-Paired Population

- Coverage rule: DIM `nodata_frac <= 0.3` and `pt_density >= 20.0 pts/m2`.
- Sensitivity: strict `0.20/30 pts/m2`, loose `0.40/10 pts/m2`.
- Failure bucket v1: `coverage`, `roof_matching_assembly_failure`, `validity`, `reference_mismatch`.
- Coverage-controlled population: both attempted, DIM coverage pass, and no reference-mismatch exclusion.

## Success Rates

| population | n | als_success | dim_success | both_success | als_only | dim_only | both_fail |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full_199 | 199 | 163/199 (81.9%) | 102/199 (51.3%) | 89/199 (44.7%) | 74/199 (37.2%) | 13/199 (6.5%) | 23/199 (11.6%) |
| both_attempted_179 | 179 | 163/179 (91.1%) | 102/179 (57.0%) | 89/179 (49.7%) | 74/179 (41.3%) | 13/179 (7.3%) | 3/179 (1.7%) |
| coverage_controlled | 93 | 84/93 (90.3%) | 75/93 (80.6%) | 67/93 (72.0%) | 17/93 (18.3%) | 8/93 (8.6%) | 1/93 (1.1%) |

## DIM Failure Bucket Summary

- DIM `no_points` classified as coverage: 46 total; 44 are paired with ALS success.
- DIM `missing_lod22_geometry` classified as coverage due to coverage miss: 8.
- DIM bucket counts, full 199: {'success': 102, 'coverage': 56, 'reference_mismatch': 21, 'roof_matching_assembly_failure': 7, 'validity': 13}

## Bucket Counts

| input | bucket_v1 | full_199_count | both_attempted_179_count | coverage_control_count |
| --- | ---: | ---: | ---: | ---: |
| ALS | success | 163 | 163 | 84 |
| ALS | coverage | 1 | 1 | 1 |
| ALS | roof_matching_assembly_failure | 0 | 0 | 0 |
| ALS | validity | 15 | 15 | 8 |
| ALS | reference_mismatch | 20 | 0 | 0 |
| DIM | success | 102 | 102 | 75 |
| DIM | coverage | 56 | 56 | 0 |
| DIM | roof_matching_assembly_failure | 7 | 7 | 7 |
| DIM | validity | 13 | 13 | 11 |
| DIM | reference_mismatch | 21 | 1 | 0 |

## Coverage Sensitivity

| sensitivity | nodata_max | density_min_pts_m2 | coverage_controlled_n | als_success | dim_success | dim_failure_coverage | dim_failure_roof_matching_assembly | dim_failure_validity |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| strict | 0.20 | 30.0 | 90 | 81/90 (90.0%) | 73/90 (81.1%) | 0 | 6 | 11 |
| base | 0.30 | 20.0 | 93 | 84/93 (90.3%) | 75/93 (80.6%) | 0 | 7 | 11 |
| loose | 0.40 | 10.0 | 96 | 86/96 (89.6%) | 77/96 (80.2%) | 1 | 7 | 11 |

## Reference Mismatch Check

| building_id | reference_mismatch_suspected | reason | action | figure | als_inside_count | als_inside_ground_ratio | als_inside_non_ground_z_p50 | dim_inside_count | dim_inside_ground_ratio | dim_inside_non_ground_z_p50 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DEBY_LOD2_104586480 | yes | DIM footprint interior is dominated by ground-class points while ALS has almost no ground-class interior; coverage is high, so the failure is treated as reference or temporal mismatch candidate. | exclude_from_coverage_control_population | docs/figs/w2_1c_DEBY_LOD2_104586480_als_dim_section.png | 199 | 0.000 | 515.115 | 15489 | 0.766 | 523.940 |

- ALS/DIM section figure: `docs/figs/w2_1c_DEBY_LOD2_104586480_als_dim_section.png`

## Files

- Updated paired CSV: `docs/W2_1c_paired_status.csv`
- Classification summary: `docs/W2_1c_failure_bucket_summary.csv`
- Success-rate table: `docs/W2_1c_success_rates.csv`
- Coverage sensitivity: `docs/W2_1c_coverage_sensitivity.csv`
- Reference mismatch exclusions: `docs/W2_1c_reference_mismatch_exclusions.csv`
