# E5 C001 ③b-S1 readout/evaluation temporary report

S1 wrapper executed base and voxel02 only. Final interpretation material is written to `docs/W_E5_C001_③b_S1_표면복원.md`.

## Summary

| setting | mean_coverage_post_sor | mean_completeness | mean_correctness | median_ref_rms_m | has_lod22 | val3dity_valid |
|---|---|---|---|---|---|---|
| base | 0.2559 | 0.3981 | 0.6667 | 3.0396 | 37 | 40 |
| voxel02 | 0.0768 | 0.1528 | 0.8538 | 1.1932 | 13 | 46 |

## Outputs

- metrics: `docs/e5_c001_3b_s1_metrics.csv`
- coverage: `docs/e5_c001_3b_s1_coverage.csv`
- inventory rows: 6
- tradeoff rows: 2
- filter rows: 6
- case rows: 24
- figures: `docs/figs/e5_c001_3b_s1/readout/coverage_recovery_summary.png`, `docs/figs/e5_c001_3b_s1/readout/coverage_accuracy_scatter.png`, `docs/figs/e5_c001_3b_s1/readout/filter_stage_contribution.png`
