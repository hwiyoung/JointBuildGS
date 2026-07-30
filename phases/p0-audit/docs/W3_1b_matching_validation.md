# W3-1b Matching Validation Addendum

- Run ID: `w3_1b_roofer_quality_20260612_212536`
- Base W3-1 run: `w3_1_roofer_quality_20260612_210850`
- Base Roofer default run: `w2_1_roofer_default_20260612_152729`
- Internal boundary metric: shared boundaries among matched roof-surface pairs, sampled every 0.50 m.
- Shared boundary extraction ignores line segments shorter than 0.20 m.

## Matching Overlay Spot Checks

| bucket | building_id | ref_roof_planes | als_plane_f1 | dim_plane_f1 | mean_plane_f1 | selection_rule | figure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| high | DEBY_LOD2_4959793 | 4 | 1.000000 | 1.000000 | 1.000000 | highest mean F1 group; tie-breaker larger ref_roof_planes | docs/evidence/p0_g1_20260613/figs/fig_07_matching_overlay_high_4959793.png |
| mid | DEBY_LOD2_4907518 | 12 | 0.500000 | 0.500000 | 0.500000 | closest to mean F1 0.5; tie-breaker larger ref_roof_planes | docs/evidence/p0_g1_20260613/figs/fig_03_figure_1_1b_ridge_4907518.png |
| low | DEBY_LOD2_4906987 | 5 | 0.000000 | 0.000000 | 0.000000 | lowest mean F1; tie-breaker larger ref_roof_planes | docs/evidence/p0_g1_20260613/figs/fig_08_matching_overlay_low_4906987.png |

![high overlay](../../../docs/evidence/p0_g1_20260613/figs/fig_07_matching_overlay_high_4959793.png)

![mid overlay](../../../docs/evidence/p0_g1_20260613/figs/fig_03_figure_1_1b_ridge_4907518.png)

![low overlay](../../../docs/evidence/p0_g1_20260613/figs/fig_08_matching_overlay_low_4906987.png)

## Internal Boundary Summary

| metric | n_paired_finite | als_median | dim_median | dim_minus_als | dim_over_als | definition |
| --- | --- | --- | --- | --- | --- | --- |
| internal_boundary_chamfer_m | 36 | 0.396221 | 0.414909 | 0.018688 | 1.047167 | matched roof-surface shared boundaries sampled at 0.50 m |
| internal_boundary_hausdorff_m | 36 | 1.439189 | 1.800416 | 0.361227 | 1.250993 | matched roof-surface shared boundaries sampled at 0.50 m |

## Height Bias Outlier Note

- Outlier building: `DEBY_LOD2_4906973`.
- Observation: both ALS and DIM Roofer outputs are about 4.8 m below the LoD2 reference roof over nearly the same XY footprint.
- Review note: this is a `reference_mismatch_candidate` consistent with possible extension/reconstruction or another reference/source-time mismatch; keep it explicit rather than mixing it with ordinary roof matching error.

| building_id | input | source_gml | ref_roof_planes | pred_roof_planes | matched_planes | plane_f1 | height_bias_m | matched_ref_median_z_m | matched_pred_median_z_m | matched_pred_minus_ref_median_m | matched_sample_count | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DEBY_LOD2_4906973 | als | 690_5334.gml | 1 | 1 | 1 | 1.000000 | -4.779279 | 524.016000 | 519.236721 | -4.779279 | 222 | LoD2 reference roof is about 4.8 m higher than both ALS and DIM Roofer outputs over the same XY footprint; mark as reference_mismatch_candidate for manual review. |
| DEBY_LOD2_4906973 | dim | 690_5334.gml | 1 | 3 | 1 | 0.500000 | -4.857638 | 524.016000 | 519.158362 | -4.857638 | 181 | LoD2 reference roof is about 4.8 m higher than both ALS and DIM Roofer outputs over the same XY footprint; mark as reference_mismatch_candidate for manual review. |

## Files

- Internal boundary metrics: `docs/W3_1b_internal_boundary_metrics.csv`
- Internal boundary summary: `docs/W3_1b_internal_boundary_summary.csv`
- Overlay selection: `docs/W3_1b_overlay_selection.csv`
- Height outlier note: `docs/W3_1b_height_outlier_note.csv`
