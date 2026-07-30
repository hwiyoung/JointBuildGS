# B104 Ground Closure Report

## Triangulation

| source | ground_cov | ground_y | gt_ground_y | evidence_ground_mean | evidence_ground_median | F | h_err | edge_ok | open_edges |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E0_GT_clean_upper_bound | 1.000 | -0.194 | -0.194 | -0.194 | -0.194 | 1.000 | 0.000 | True | 0 |
| E1_Baseline_rendered | 1.000 | -0.524 | -0.194 | -0.498 | -0.307 | 1.000 | 0.231 | True | 0 |
| E2_Mutual_rendered | 0.000 | -0.931 | -0.194 | -0.865 | -0.666 | 0.828 | 0.612 | True | 0 |
| E4_Mutual_primitive | 0.000 | -2.827 | -0.194 | NA | NA | 0.565 | 2.558 | True | 0 |

## Classification

B104 is classified as a `Stage3 algorithm issue` with a contributing rendered evidence/support issue. E0 is perfect and E1 is acceptable, while E2 and E4 produce closed shells with GroundSurface present but ground coverage at 0. The concrete Stage3 weakness is the weighted-mean ground height rule over noisy class-3 rendered points.

## Intervention

`v1c-ground` changes only the read-out ground height estimator to a robust weighted median of explicit class-3 evidence. It does not synthesize ground when class-3 evidence is absent and does not modify Stage2 evidence.

## Ablation Outcome

`v1c-ground` decision: `REJECT`. Reason: Robust ground branch did not satisfy recovery/no-regression gate.
