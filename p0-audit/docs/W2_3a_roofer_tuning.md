# W2-3a Roofer Input-Specific Tuning

- Run ID: `w2_3a_roofer_tuning_20260612_202013`
- Coverage-control population: 93 buildings from `docs/W2_1c_paired_status.csv`.
- Dev subset: 15 buildings, random seed `20260612`. Dev rows are reported separately from the non-dev evaluation subset.
- Selection rule fixed before tuning: maximize dev `status=success`, then LoD2.2 generated count, val3dity-valid count, lower mean `rf_rmse_lod22`, then lower complexity/epsilon/min-points.
- Roofer grid parameters: `plane-detect-epsilon`, `plane-detect-min-points`, `complexity-factor`; plumbing kept fixed (`--id-attribute`, AOI `--box`, `--filter`, `--jobs`).

## Selected Parameters

| input | selected_config_id | plane_detect_epsilon | plane_detect_min_points | complexity_factor | dev_n | dev_success | dev_success_rate | dev_lod22_generated | dev_lod22_rate | dev_val3dity_valid | dev_valid_rate | dev_mean_rf_rmse_lod22 | selection_basis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALS | default | 0.3 | 15 | 0.888 | 15 | 15 | 100.0% | 15 | 100.0% | 15 | 100.0% | 1.188927 | max success, then LoD2.2 count, validity count, lower RMSE, lower complexity/epsilon/min-points |
| DIM | default | 0.3 | 15 | 0.888 | 15 | 13 | 86.7% | 13 | 86.7% | 15 | 100.0% | 1.194971 | max success, then LoD2.2 count, validity count, lower RMSE, lower complexity/epsilon/min-points |

## Interpretation Note

Both inputs selected Roofer default parameters on the dev subset. The full-93 deltas below are therefore selected-default filtered rerun deltas against the W2-1c baseline table, not evidence that a non-default tuning setting improved reconstruction.

## Dev Grid Results

| input | config_id | epsilon | min_points | complexity | success | lod22 | valid | mean_rmse | selected |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALS | default | 0.3 | 15 | 0.888 | 15 | 15 | 15 | 1.188927 | yes |
| ALS | simple_loose_min10 | 0.45 | 10 | 0.65 | 15 | 15 | 15 | 1.256519 | no |
| ALS | simple_strict_min10 | 0.25 | 10 | 0.65 | 14 | 15 | 14 | 1.243002 | no |
| ALS | simple_loose_min20 | 0.45 | 20 | 0.65 | 15 | 15 | 15 | 1.258561 | no |
| ALS | simple_strict_min20 | 0.25 | 20 | 0.65 | 14 | 15 | 14 | 1.250163 | no |
| ALS | detail_loose_min10 | 0.45 | 10 | 0.95 | 15 | 15 | 15 | 1.189708 | no |
| ALS | detail_strict_min10 | 0.25 | 10 | 0.95 | 14 | 15 | 14 | 1.173302 | no |
| ALS | detail_loose_min20 | 0.45 | 20 | 0.95 | 13 | 15 | 13 | 1.189783 | no |
| ALS | detail_strict_min20 | 0.25 | 20 | 0.95 | 14 | 15 | 14 | 1.185599 | no |
| DIM | default | 0.3 | 15 | 0.888 | 13 | 13 | 15 | 1.194971 | yes |
| DIM | simple_loose_min10 | 0.45 | 10 | 0.65 | 13 | 13 | 15 | 1.221760 | no |
| DIM | simple_strict_min10 | 0.25 | 10 | 0.65 | 13 | 13 | 15 | 1.226087 | no |
| DIM | simple_loose_min20 | 0.45 | 20 | 0.65 | 13 | 13 | 15 | 1.219430 | no |
| DIM | simple_strict_min20 | 0.25 | 20 | 0.65 | 13 | 13 | 15 | 1.211411 | no |
| DIM | detail_loose_min10 | 0.45 | 10 | 0.95 | 7 | 13 | 9 | 1.192140 | no |
| DIM | detail_strict_min10 | 0.25 | 10 | 0.95 | 11 | 13 | 13 | 1.184835 | no |
| DIM | detail_loose_min20 | 0.45 | 20 | 0.95 | 9 | 13 | 11 | 1.197270 | no |
| DIM | detail_strict_min20 | 0.25 | 20 | 0.95 | 11 | 13 | 13 | 1.188881 | no |

## Default vs Tuned Success

| population | input | n | default_success | tuned_success | delta_count | delta_percentage_points |
| --- | --- | --- | --- | --- | --- | --- |
| coverage_control_93_all | ALS | 93 | 84/93 (90.3%) | 87/93 (93.5%) | 3 | +3.2 |
| coverage_control_93_all | DIM | 93 | 75/93 (80.6%) | 76/93 (81.7%) | 1 | +1.1 |
| coverage_control_93_all | PAIRED_BOTH_SUCCESS | 93 | 67/93 (72.0%) | 72/93 (77.4%) | 5 | +5.4 |
| dev15_tuning_subset | ALS | 15 | 15/15 (100.0%) | 15/15 (100.0%) | 0 | +0.0 |
| dev15_tuning_subset | DIM | 15 | 12/15 (80.0%) | 13/15 (86.7%) | 1 | +6.7 |
| dev15_tuning_subset | PAIRED_BOTH_SUCCESS | 15 | 12/15 (80.0%) | 13/15 (86.7%) | 1 | +6.7 |
| eval78_non_dev | ALS | 78 | 69/78 (88.5%) | 72/78 (92.3%) | 3 | +3.8 |
| eval78_non_dev | DIM | 78 | 63/78 (80.8%) | 63/78 (80.8%) | 0 | +0.0 |
| eval78_non_dev | PAIRED_BOTH_SUCCESS | 78 | 55/78 (70.5%) | 59/78 (75.6%) | 4 | +5.1 |

## Failure Bucket Reclassification

| population | input | bucket_v1 | default_count | tuned_count |
| --- | --- | --- | --- | --- |
| coverage_control_93_all | ALS | success | 84 | 87 |
| coverage_control_93_all | ALS | coverage | 1 | 1 |
| coverage_control_93_all | ALS | validity | 8 | 5 |
| coverage_control_93_all | DIM | success | 75 | 76 |
| coverage_control_93_all | DIM | roof_matching_assembly_failure | 7 | 8 |
| coverage_control_93_all | DIM | validity | 11 | 9 |
| dev15_tuning_subset | ALS | success | 15 | 15 |
| dev15_tuning_subset | DIM | success | 12 | 13 |
| dev15_tuning_subset | DIM | roof_matching_assembly_failure | 2 | 2 |
| dev15_tuning_subset | DIM | validity | 1 | 0 |
| eval78_non_dev | ALS | success | 69 | 72 |
| eval78_non_dev | ALS | coverage | 1 | 1 |
| eval78_non_dev | ALS | validity | 8 | 5 |
| eval78_non_dev | DIM | success | 63 | 63 |
| eval78_non_dev | DIM | roof_matching_assembly_failure | 5 | 6 |
| eval78_non_dev | DIM | validity | 10 | 9 |

## Files

- Dev subset: `docs/W2_3a_dev_subset.csv`
- Dev grid table: `docs/W2_3a_grid_results.csv`
- Selected parameters: `docs/W2_3a_selected_params.csv`
- Tuned paired status: `docs/W2_3a_tuned_paired_status.csv`
- Default vs tuned success: `docs/W2_3a_paired_success.csv`
- Bucket summary: `docs/W2_3a_bucket_summary.csv`
