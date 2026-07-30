# FC-S6E Joint Screening Report

## Status

`COMPLETE`

## Compared Arms

- A8 legacy terrain-off reference: existing FC-S6 rows
- A8_v2_geo: existing FC-S6D-2 rows
- A8_v2_joint_2pct: FC-S6E screening run

## Completion: `10/10` OK rows

## Split Summary

| run | split | status | mean_F | support_cov | ground_support_cov |
|---|---|---|---:|---:|---:|
| A8_no_terrain_terms | all_10 | OK | 0.8287070118496714 | 0.46699999999999997 | 0.17229999999999998 |
| A8_no_terrain_terms | easy_control | OK | 0.9521377550474762 | 0.5183333333333333 | 0.14479999999999998 |
| A8_no_terrain_terms | hard_diagnostic | OK | 0.7052762686518668 | 0.41566666666666663 | 0.19980000000000003 |
| A8_no_terrain_terms | guard_bids | OK | 0.7958429741571338 | 0.4572083333333333 | 0.18512499999999998 |
| A8_no_terrain_terms | roof_complex | OK | 0.5346069265415375 | 0.304 | 0.113 |
| A8_no_terrain_terms | terrain_sensitive | OK | 0.9507967607407607 | 0.5486666666666666 | 0.26 |
| A8_v2_geo | all_10 | OK | 0.8215049456030936 | 0.4766 | 0.1776 |
| A8_v2_geo | easy_control | OK | 0.9420177343896213 | 0.5296 | 0.16899999999999998 |
| A8_v2_geo | hard_diagnostic | OK | 0.7009921568165659 | 0.4236000000000001 | 0.1862 |
| A8_v2_geo | guard_bids | OK | 0.7961315552487309 | 0.46791666666666665 | 0.18562499999999998 |
| A8_v2_geo | roof_complex | OK | 0.5279155576069856 | 0.30922222222222223 | 0.11466666666666668 |
| A8_v2_geo | terrain_sensitive | OK | 0.9523731640671779 | 0.552 | 0.22933333333333336 |
| A8_v2_joint_2pct | all_10 | OK | 0.7941223181020503 | 0.4099666666666667 | 0.1825 |
| A8_v2_joint_2pct | easy_control | OK | 0.9078495802477707 | 0.4440666666666667 | 0.1678 |
| A8_v2_joint_2pct | hard_diagnostic | OK | 0.6803950559563297 | 0.3758666666666667 | 0.1972 |
| A8_v2_joint_2pct | guard_bids | OK | 0.7734904026104119 | 0.406625 | 0.190125 |
| A8_v2_joint_2pct | roof_complex | OK | 0.5246402364082097 | 0.2933333333333333 | 0.116 |
| A8_v2_joint_2pct | terrain_sensitive | OK | 0.9120098698528598 | 0.4543333333333333 | 0.25033333333333335 |

## Decision

`D3_KEEP_A8_LEGACY`

This is based on Stage3Algo-v1 + Metric-v1 outputs only. Viewer QA remains required before any downstream Lmu7 smoke claim.
