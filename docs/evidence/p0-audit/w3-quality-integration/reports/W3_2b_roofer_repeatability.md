# W3-2b Roofer Default Repeatability

- Run ID: `w3_2b_roofer_repeatability_20260612_220747`
- Existing run used as run 1: `w2_3a_roofer_tuning_20260612_202013` `full93/default`.
- Added runs: `run_2` and `run_3` in the run directory above.
- Population: W2-1c coverage-control set, 93 buildings.
- Roofer settings: explicit default `plane-detect-epsilon=0.30`, `plane-detect-min-points=15`, `complexity-factor=0.888`, `--jobs 32`, same AOI `--box`, same `--filter` list.

## Success Rates

| run_label | source_run_id | metric | n | success_count | success_rate | success_rate_pp |
| --- | --- | --- | --- | --- | --- | --- |
| run_1_existing | w2_3a_roofer_tuning_20260612_202013 | ALS | 93 | 87 | 87/93 (93.5%) | 93.548387 |
| run_1_existing | w2_3a_roofer_tuning_20260612_202013 | DIM | 93 | 76 | 76/93 (81.7%) | 81.720430 |
| run_1_existing | w2_3a_roofer_tuning_20260612_202013 | PAIRED_BOTH_SUCCESS | 93 | 72 | 72/93 (77.4%) | 77.419355 |
| run_2 | w3_2b_roofer_repeatability_20260612_220747 | ALS | 93 | 87 | 87/93 (93.5%) | 93.548387 |
| run_2 | w3_2b_roofer_repeatability_20260612_220747 | DIM | 93 | 75 | 75/93 (80.6%) | 80.645161 |
| run_2 | w3_2b_roofer_repeatability_20260612_220747 | PAIRED_BOTH_SUCCESS | 93 | 71 | 71/93 (76.3%) | 76.344086 |
| run_3 | w3_2b_roofer_repeatability_20260612_220747 | ALS | 93 | 87 | 87/93 (93.5%) | 93.548387 |
| run_3 | w3_2b_roofer_repeatability_20260612_220747 | DIM | 93 | 75 | 75/93 (80.6%) | 80.645161 |
| run_3 | w3_2b_roofer_repeatability_20260612_220747 | PAIRED_BOTH_SUCCESS | 93 | 71 | 71/93 (76.3%) | 76.344086 |

## Run Noise

| metric | n_runs | min_success_rate_pp | max_success_rate_pp | mean_success_rate_pp | range_pp | half_range_pp | success_count_values |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ALS | 3 | 93.548387 | 93.548387 | 93.548387 | 0.000000 | 0.000000 | 87;87;87 |
| DIM | 3 | 80.645161 | 81.720430 | 81.003584 | 1.075269 | 0.537634 | 76;75;75 |
| PAIRED_BOTH_SUCCESS | 3 | 76.344086 | 77.419355 | 76.702509 | 1.075269 | 0.537634 | 72;71;71 |

- Noise conclusion: Same-settings Roofer default run noise over three 93-building runs is +/-0.5 pp by half-range, with the maximum on DIM.

## Unstable Building Results

- Buildings with any input or paired-category change across runs: 1.

| building_id | unstable_fields | als_sequence | dim_sequence | pair_sequence |
| --- | --- | --- | --- | --- |
| DEBY_LOD2_60042 | DIM;PAIR | success:success -> success:success -> success:success | success:success -> failure:val3dity_invalid -> failure:val3dity_invalid | both_success -> ALS_only -> ALS_only |

## Files

- Success-rate table: `docs/W3_2b_roofer_repeatability_success.csv`
- Building-level status table: `docs/W3_2b_roofer_repeatability_building_status.csv`
- Unstable building list: `docs/W3_2b_roofer_repeatability_unstable_buildings.csv`
- Noise table: `docs/W3_2b_roofer_repeatability_noise.csv`
