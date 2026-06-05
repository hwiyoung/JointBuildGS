# FC-S6D Directional Screening Report

## Status

`COMPLETE`

## Compared Arms
- A8 legacy terrain-off reference: existing FC-S6 rows
- A8_v2_geo: FC-S6D-2 screening run

## A8_v2_geo Completion
- OK rows: `10/10`
- Metrics CSV: `results/FC_S6D_directional_screening/phase3_eval/a8_v2_geo_metrics_by_bid.csv`
- Split summary: `results/FC_S6D_directional_screening/phase3_eval/a8_v2_geo_split_summary.csv`

## Split Summary

| split | status | mean_F | mean_support_cov | mean_ground_support_cov |
|---|---|---:|---:|---:|
| all_10 | OK | 0.8215049456030936 | 0.4766 | 0.1776 |
| easy_control | OK | 0.9420177343896213 | 0.5296 | 0.16899999999999998 |
| hard_diagnostic | OK | 0.7009921568165659 | 0.4236000000000001 | 0.1862 |
| guard_bids | OK | 0.7961315552487309 | 0.46791666666666665 | 0.18562499999999998 |
| roof_complex | OK | 0.5279155576069856 | 0.30922222222222223 | 0.11466666666666668 |
| terrain_sensitive | OK | 0.9523731640671779 | 0.552 | 0.22933333333333336 |

## B104 Guard
- status: `OK`
- ground_cov: `1.0`
- ground_support_cov: `0.459`
- open_edges: `0`
- non_manifold_edges: `0`

No L_structure, G2, A8_v2_joint, or Lmu7 run was started by this experiment.
