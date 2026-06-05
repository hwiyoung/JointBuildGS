# Rendered Support Attribution Report

## Classwise Support

| bid | source | support_cov | roof_support_cov | wall_support_cov | ground_support_cov | F |
| --- | --- | --- | --- | --- | --- | --- |
| B104 | E1_Baseline_rendered | 0.794 | 1.000 | 0.775 | 0.545 | 1.000 |
| B104 | E2_Mutual_rendered | 0.745 | 1.000 | 0.831 | 0.386 | 0.828 |
| B6 | E1_Baseline_rendered | 0.463 | 0.898 | 0.421 | 0.071 | 0.948 |
| B6 | E2_Mutual_rendered | 0.417 | 0.740 | 0.381 | 0.064 | 0.931 |
| B3 | E1_Baseline_rendered | 0.253 | 0.321 | 0.407 | 0.065 | 0.403 |
| B3 | E2_Mutual_rendered | 0.255 | 0.301 | 0.443 | 0.066 | 0.438 |
| B123 | E1_Baseline_rendered | 0.342 | 0.302 | 0.652 | 0.102 | 0.597 |
| B123 | E2_Mutual_rendered | 0.312 | 0.289 | 0.603 | 0.079 | 0.576 |
| B126 | E1_Baseline_rendered | 0.235 | 0.200 | 0.449 | 0.045 | 0.561 |
| B126 | E2_Mutual_rendered | 0.247 | 0.267 | 0.488 | 0.045 | 0.540 |

## Classification

Rendered support attribution is classified as a `Stage2 rendered evidence/support issue`. E1 and E2 often have closed shells and reasonable GT metrics while classwise support, especially ground support, remains low because rendered class-3 evidence is sparse or vertically noisy. No Stage3 patch is selected for support attribution.
