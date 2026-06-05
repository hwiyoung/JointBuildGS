# FC-S3 Phase 1: Full E1-vs-E2 Comparison

Controlled baseline: Stage3Algo-v1 + Metric-v1. No rejected v1c branch is used.

## Summary
- All 10 OK count: E1=10/10, E2=10/10.
- Mean F all 10: E1=0.822, E2=0.803, raw E2-E1=-0.018.
- Mean F easier/control: E1=0.942, E2=0.944, raw E2-E1=0.002.
- Mean F hard diagnostic: E1=0.702, E2=0.663, raw E2-E1=-0.039.

## Win/Loss
| metric | E2 wins | E1 wins | ties | direction |
| --- | --- | --- | --- | --- |
| ok | 0 | 0 | 10 | higher_better |
| F | 4 | 6 | 0 | higher_better |
| precision | 4 | 6 | 0 | higher_better |
| recall | 4 | 6 | 0 | higher_better |
| roof_cov | 5 | 3 | 2 | higher_better |
| wall_cov | 5 | 4 | 1 | higher_better |
| ground_cov | 2 | 4 | 4 | higher_better |
| support_cov | 4 | 6 | 0 | higher_better |
| roof_support_cov | 3 | 4 | 3 | higher_better |
| wall_support_cov | 4 | 6 | 0 | higher_better |
| ground_support_cov | 3 | 7 | 0 | higher_better |
| h_err | 6 | 4 | 0 | lower_better |
| vol_ratio | 6 | 4 | 0 | closer_to_1 |
| chamfer | 4 | 6 | 0 | lower_better |
| hausdorff | 3 | 7 | 0 | lower_better |
| open_edges | 0 | 0 | 10 | lower_better |
| non_manifold_edges | 0 | 0 | 10 | lower_better |

## Focus Bid Deltas
| bid | dF | droof | dwall | dground | dsupport | dh_err |
| --- | --- | --- | --- | --- | --- | --- |
| B2 | -0.003 | 0.000 | 0.001 | 0.000 | -0.016 | -0.052 |
| B6 | -0.016 | -0.145 | -0.001 | 0.000 | -0.045 | -0.238 |
| B3 | 0.035 | 0.006 | 0.013 | 0.120 | 0.003 | -0.651 |
| B123 | -0.020 | -0.017 | -0.007 | -0.030 | -0.030 | -0.237 |
| B126 | -0.021 | 0.014 | 0.000 | -0.028 | 0.012 | -0.091 |
| B104 | -0.172 | 0.000 | -0.083 | -1.000 | -0.049 | 0.381 |

## Interpretation
E2 is treated as supported only where directional wins appear in final geometry/support metrics, not just in proxy evidence statistics.
