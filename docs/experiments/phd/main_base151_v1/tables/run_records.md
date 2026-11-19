# run_records

3.2: per run x cell x attempt (queue receipt, entry trace every 1000 iterations, PSNR of the official log at 30000; 2DGS = one model scored with both priors)

scientific_verdict: null

| run | method | prior | cell | attempt | status | exit_code | hours | last_iteration | gaussians_final | gaussians_max | elong_lt_001_final | cap_GiB | gpu_free_MiB_at_launch | cuda_peak_reserved_GiB | host_rss_peak_GiB | cgroup_peak_GiB | min_gpu1_free_MiB | min_host_available_GiB | psnr_test_30000 | psnr_train_30000 | pause | resume_from | host_guard | gpu_pause | gpu_kill |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b151_2DGS_s0 | 2DGS | ALS + LoD2 (one model) | 0 | 1 | TRAINING_COMPLETE | 0 | 0.89 | 30000 | 2153433 | 2153433 | 0.00 | 21.52 | 24086 | 7.47 | 10.51 | 10.25 | 16087 | 34.10 | 21.90 | 24.19 |  |  |  |  |  |
| b151_2DGS_s0 | 2DGS | ALS + LoD2 (one model) | 1 | 1 | TRAINING_COMPLETE | 0 | 0.69 | 30000 | 1724133 | 1724133 | 0.00 | 21.52 | 24086 | 5.53 | 13.64 | 13.61 | 18067 | 25.50 | 21.05 | 22.63 |  |  |  |  |  |
| b151_2DGS_s0 | 2DGS | ALS + LoD2 (one model) | 2 | 1 | TRAINING_COMPLETE | 0 | 0.61 | 30000 | 1732898 | 1732898 | 0.00 | 21.52 | 24086 | 5.42 | 15.36 | 15.32 | 18187 | 43.60 | 21.34 | 23.26 |  |  |  |  |  |
| b151_2DGS_s0 | 2DGS | ALS + LoD2 (one model) | 3 | 1 | TRAINING_COMPLETE | 0 | 0.95 | 30000 | 4516553 | 4516553 | 0.01 | 21.52 | 24086 | 10.80 | 13.41 | 13.32 | 12667 | 47.70 | 22.60 | 25.21 |  |  |  |  |  |
| b151_GeoGS_ALS_s0 | GeoGS | ALS | 0 | 1 | TRAINING_COMPLETE | 0 | 1.34 | 30000 | 3069956 | 3069956 | 0.01 | 21.52 | 24086 | 12.10 | 12.23 | 12.42 | 6240 | 37.80 | 22.23 | 24.04 |  |  |  |  |  |
| b151_GeoGS_ALS_s0 | GeoGS | ALS | 1 | 1 | TRAINING_COMPLETE | 0 | 1.15 | 30000 | 2621151 | 2621151 | 0.00 | 21.51 | 24070 | 11.36 | 15.31 | 15.85 | 11092 | 29.70 | 21.87 | 23.36 |  |  |  |  |  |
| b151_GeoGS_ALS_s0 | GeoGS | ALS | 2 | 1 | TRAINING_COMPLETE | 0 | 1.00 | 30000 | 2570824 | 2570824 | 0.00 | 21.51 | 24070 | 12.16 | 17.30 | 17.27 | 10270 | 36.80 | 22.09 | 23.01 |  |  |  |  |  |
| b151_GeoGS_ALS_s0 | GeoGS | ALS | 3 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_GeoGS_LoD2_s0 | GeoGS | LoD2 | 0 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_GeoGS_LoD2_s0 | GeoGS | LoD2 | 1 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_GeoGS_LoD2_s0 | GeoGS | LoD2 | 2 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_GeoGS_LoD2_s0 | GeoGS | LoD2 | 3 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_CDGS_ALS_s0 | CDGS | ALS | 0 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_CDGS_ALS_s0 | CDGS | ALS | 1 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_CDGS_ALS_s0 | CDGS | ALS | 2 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_CDGS_ALS_s0 | CDGS | ALS | 3 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_CDGS_LoD2_s0 | CDGS | LoD2 | 0 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_CDGS_LoD2_s0 | CDGS | LoD2 | 1 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_CDGS_LoD2_s0 | CDGS | LoD2 | 2 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| b151_CDGS_LoD2_s0 | CDGS | LoD2 | 3 |  | NO_RECEIPT (running or waiting) |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
