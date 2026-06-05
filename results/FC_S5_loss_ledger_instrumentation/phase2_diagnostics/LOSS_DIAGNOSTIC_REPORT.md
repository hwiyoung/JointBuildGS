# FC-S5 Loss Diagnostic Report

## Status

Current diagnostic state is derived from the metrics CSVs and job records. M3 Stage2 training has completed and its Stage3Algo-v1 + Metric-v1 evaluation is being run separately. M5/M10 are handled by the remaining background chain.

## Current Run State

| run | status | completed OK rows | mean F | mean ground_cov | note |
| --- | --- | ---: | ---: | ---: | --- |
| M3 | EVALUATED | 10/10 | 0.812 | 0.873 | Reduced mutual weight; tests whether original mutual was too strong. |
| M5 | EVALUATED | 10/10 | 0.828 | 0.884 | Terrain terms disabled; tests B104-like terrain drift. |
| M10 | EVALUATED | 10/10 | 0.821 | 0.904 | Ramped mutual; tests early-geometry disturbance. |

## B104 Terrain Drift

| run | job_status | ground_cov | ground_support_cov | terrain_drift_status |
| --- | --- | ---: | ---: | --- |
| M3 | COMPLETED | 1.000 | 0.486 | RECOVERED_TO_E1 |
| M5 | COMPLETED | 1.000 | 0.510 | RECOVERED_TO_E1 |
| M10 | COMPLETED | 1.000 | 0.488 | RECOVERED_TO_E1 |

## Split Summary

| run | split | status | mean_F | mean_ground_cov | mean_ground_support_cov |
| --- | --- | --- | ---: | ---: | ---: |
| M3 | all_10 | OK | 0.812 | 0.873 | 0.181 |
| M3 | easy_control | OK | 0.932 | 0.800 | 0.169 |
| M3 | hard_diagnostic | OK | 0.692 | 0.946 | 0.194 |
| M3 | guard_bids | OK | 0.787 | 0.966 | 0.189 |
| M5 | all_10 | OK | 0.828 | 0.884 | 0.180 |
| M5 | easy_control | OK | 0.952 | 0.800 | 0.171 |
| M5 | hard_diagnostic | OK | 0.703 | 0.968 | 0.190 |
| M5 | guard_bids | OK | 0.805 | 0.980 | 0.188 |
| M10 | all_10 | OK | 0.821 | 0.904 | 0.177 |
| M10 | easy_control | OK | 0.954 | 0.876 | 0.169 |
| M10 | hard_diagnostic | OK | 0.688 | 0.932 | 0.185 |
| M10 | guard_bids | OK | 0.796 | 0.957 | 0.183 |

## Selection Gate State

M5 is the current candidate by all-10 mean F gate.

No final mutual candidate should be accepted until all-10, easy/control, hard diagnostic, B104 terrain, support, and topology gates are evaluated.
