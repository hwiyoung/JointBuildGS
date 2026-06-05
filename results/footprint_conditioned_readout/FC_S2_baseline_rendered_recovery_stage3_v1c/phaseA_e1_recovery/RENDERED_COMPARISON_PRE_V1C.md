# Rendered Baseline vs Mutual Pre-v1c

## Scope

- E1 artifact: `results/footprint_conditioned_readout/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery/E1_Baseline_rendered.npz`
- Output root: `results/footprint_conditioned_readout/FC_S2_baseline_rendered_recovery_stage3_v1c/phaseA_e1_recovery`
- Stage3 algorithms were not modified.
- Metric-v1 was not modified.
- Track B patches were not started.
- Footprint/domain, source definitions, gravity, and Stage2 evidence generation are unchanged.

## E1 Stage3 matrix

| algo | metric | source | rows | OK | mean_F | mean_roof_cov | mean_wall_cov | mean_ground_cov | mean_support_cov |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage3Algo-v0 | Metric-v0 | E1_Baseline_rendered | 10 | 10 | 0.821 | 0.628 | 0.855 | 0.876 | 0.465 |
| Stage3Algo-v0 | Metric-v1 | E1_Baseline_rendered | 10 | 10 | 0.822 | 0.624 | 0.855 | 0.874 | 0.459 |
| Stage3Algo-v1 | Metric-v0 | E1_Baseline_rendered | 10 | 10 | 0.821 | 0.628 | 0.855 | 0.876 | 0.465 |
| Stage3Algo-v1 | Metric-v1 | E1_Baseline_rendered | 10 | 10 | 0.822 | 0.624 | 0.855 | 0.874 | 0.459 |

## Rendered comparison

- E1 Baseline rendered OK count: `OK 10/10`
- E2 Mutual rendered OK count: `OK 10/10`
- Both OK count: `10/10`

| metric | baseline_mean | mutual_mean | delta_mutual_minus_baseline |
| --- | --- | --- | --- |
| roof_cov | 0.624 | 0.609 | -0.015 |
| wall_cov | 0.855 | 0.854 | -0.001 |
| ground_cov | 0.874 | 0.837 | -0.037 |
| support_cov | 0.459 | 0.449 | -0.010 |
| roof_support_cov | 0.737 | 0.724 | -0.013 |
| wall_support_cov | 0.507 | 0.514 | 0.007 |
| ground_support_cov | 0.133 | 0.110 | -0.023 |
| F | 0.822 | 0.803 | -0.018 |
| h_err | 1.092 | 0.908 | -0.184 |
| vol_ratio | 1.034 | 1.019 | -0.015 |
| chamfer | 0.458 | 0.458 | -0.001 |
| edge_ok | 1.000 | 1.000 | 0.000 |
| open_edges | 0.000 | 0.000 | 0.000 |
| nonmanifold_edges | 0.000 | 0.000 | 0.000 |
| roof_wall_adjacency_count | 15.300 | 15.300 | 0.000 |
| wall_ground_adjacency_count | 15.300 | 15.300 | 0.000 |

## Focus bid deltas

Deltas are raw `mutual - baseline` values under `Stage3Algo-v1 + Metric-v1`.

| bid | roof_cov | wall_cov | ground_cov | support_cov | F | h_err | vol_ratio | chamfer | open_edges |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B2 | 0.000 | 0.001 | 0.000 | -0.016 | -0.003 | -0.052 | 0.010 | 0.003 | 0.000 |
| B6 | -0.145 | -0.001 | 0.000 | -0.045 | -0.016 | -0.238 | -0.014 | 0.000 | 0.000 |
| B3 | 0.006 | 0.013 | 0.120 | 0.003 | 0.035 | -0.651 | 0.008 | -0.009 | 0.000 |
| B123 | -0.017 | -0.007 | -0.030 | -0.030 | -0.020 | -0.237 | -0.254 | 0.028 | 0.000 |
| B126 | 0.014 | 0.000 | -0.028 | 0.012 | -0.021 | -0.091 | 0.212 | 0.008 | 0.000 |
| B104 | 0.000 | -0.083 | -1.000 | -0.049 | -0.172 | 0.381 | -0.131 | 0.088 | 0.000 |

## Artifacts

- `e1_stage3_matrix_metrics_by_bid.csv`
- `e1_readout_status.csv`
- `rendered_baseline_vs_mutual_pre_v1c.csv`

## Conclusion

E1_Baseline_rendered is integrated into the Stage3 matrix for the requested combinations. A rendered Baseline-vs-Mutual comparison is possible before Stage3-v1c patches because both rendered sources have Stage3Algo-v1 + Metric-v1 rows over the full FC-S1 target set.
