# E5 C001 ③b-S1 readout/evaluation temporary report

S1 wrapper executed base and voxel02 only. Final interpretation material is written to `docs/W_E5_C001_③b_S1_표면복원.md`.

## Summary

| setting | mean_coverage_post_sor | mean_completeness | mean_correctness | median_ref_rms_m | has_lod22 | val3dity_valid |
|---|---|---|---|---|---|---|
| base | 0.1506 | 0.2593 | 0.5637 | 4.3230 | 30 | 41 |
| voxel02 | 0.0595 | 0.0926 | 0.6458 | 3.1289 | 8 | 34 |

## Outputs

- metrics: `docs/e5_c001_corrected_s1_building_8way.csv`
- coverage: `docs/e5_c001_corrected_s1_coverage.csv`
- inventory rows: 6
- tradeoff rows: 2
- filter rows: 6
- case rows: 24
- figures: `docs/figs/e5_c001_corrected_s1/readout/coverage_recovery_summary.png`, `docs/figs/e5_c001_corrected_s1/readout/coverage_accuracy_scatter.png`, `docs/figs/e5_c001_corrected_s1/readout/filter_stage_contribution.png`
