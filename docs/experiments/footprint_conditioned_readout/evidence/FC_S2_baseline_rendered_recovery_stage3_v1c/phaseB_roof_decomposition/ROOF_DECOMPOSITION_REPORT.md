# Roof Decomposition Report

## E0/E1/E2 Triangulation

| bid | source | roof_cov | n_roof_faces | gt_roof_faces | F | chamfer | edge_ok | open_edges |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B3 | E0_GT_clean_upper_bound | 0.137 | 40 | 25 | 0.433 | 1.135 | True | 0 |
| B3 | E1_Baseline_rendered | 0.150 | 40 | 25 | 0.403 | 1.085 | True | 0 |
| B3 | E2_Mutual_rendered | 0.156 | 40 | 25 | 0.438 | 1.076 | True | 0 |
| B123 | E0_GT_clean_upper_bound | 0.236 | 26 | 7 | 0.629 | 0.791 | True | 0 |
| B123 | E1_Baseline_rendered | 0.167 | 26 | 7 | 0.597 | 0.835 | True | 0 |
| B123 | E2_Mutual_rendered | 0.150 | 26 | 7 | 0.576 | 0.863 | True | 0 |
| B126 | E0_GT_clean_upper_bound | 0.155 | 23 | 18 | 0.564 | 1.060 | True | 0 |
| B126 | E1_Baseline_rendered | 0.141 | 23 | 18 | 0.561 | 1.030 | True | 0 |
| B126 | E2_Mutual_rendered | 0.156 | 23 | 18 | 0.540 | 1.038 | True | 0 |

## Classification

B3/B123/B126 are classified as `unresolved` between Stage3 roof decomposition and evaluator/reference matching. E0 clean upper-bound rows already have low roof coverage while topology remains closed, so the failure is not specific to rendered evidence or Mutual training. A roof merge/prune patch is not selected because it can improve a scalar roof metric by destroying meaningful roof topology.

## Branch Decision

`v1c-roof-merge-prune` and `v1c-roof-evaluator-matching` are diagnostic no-ops. Metric-v1 is kept unchanged.
