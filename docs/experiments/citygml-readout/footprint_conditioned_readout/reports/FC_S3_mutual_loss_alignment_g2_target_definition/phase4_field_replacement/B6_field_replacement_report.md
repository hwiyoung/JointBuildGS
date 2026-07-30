# B6 Field Replacement Report

Diagnostic-only counterfactuals for height definition. Shared E0/E1/E2 height deficit remains a Stage3/evaluator issue candidate.

| replacement | status | F | roof | wall | ground | support | h_err |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FR0_E1_original | OK | 0.948 | 0.669 | 0.933 | 1.000 | 0.463 | 3.627 |
| FR1_E2_original | OK | 0.931 | 0.525 | 0.932 | 1.000 | 0.417 | 3.389 |
| FR2_E1_xyz_E2_semantic_normal | OK | 0.951 | 0.685 | 0.933 | 1.000 | 0.468 | 3.416 |
| FR3_E2_xyz_E1_semantic_normal | OK | 0.934 | 0.543 | 0.935 | 1.000 | 0.411 | 3.146 |
| FR4_E2_with_E1_ground_y_distribution | OK | 0.929 | 0.525 | 0.924 | 1.000 | 0.415 | 3.645 |
| FR5_E2_clipped_ground_y_quantiles | OK | 0.932 | 0.525 | 0.932 | 1.000 | 0.422 | 3.207 |
| FR6_E1_with_E2_semantic_entropy_confidence | OK | 0.948 | 0.669 | 0.933 | 1.000 | 0.463 | 3.627 |
| FR7_E2_with_E1_support_weight_calibration | OK | 0.931 | 0.525 | 0.932 | 1.000 | 0.417 | 3.389 |
