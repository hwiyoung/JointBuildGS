# B6 Height Definition Report

## Triangulation

| source | F | h_err | gt_height | pred_height | roof_cov | ground_cov | edge_ok | open_edges |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E0_GT_clean_upper_bound | 0.937 | 3.607 | 19.912 | 16.305 | 0.576 | 1.000 | True | 0 |
| E1_Baseline_rendered | 0.948 | 3.627 | 19.912 | 16.285 | 0.669 | 1.000 | True | 0 |
| E2_Mutual_rendered | 0.931 | 3.389 | 19.912 | 16.523 | 0.525 | 1.000 | True | 0 |

## Classification

B6 is classified as a `Stage3 algorithm issue`, but no safe minimal v1c patch is selected. E0, E1, and E2 all show the same height deficit pattern with closed topology, which rules out rendered-only evidence as the primary cause. The current height-field roof triangulation misses interior roof extrema; adding that safely would require a constrained roof-mesh change beyond the allowed minimal branch.

## Branch Decision

`v1c-height-definition` is rejected as a no-op in this run rather than changing Metric-v1 or adding a risky roof triangulation rewrite.
