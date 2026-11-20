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
| b151_GeoGS_ALS_s0 | GeoGS | ALS | 3 | 1 | TRAINING_COMPLETE | 0 | 1.25 | 30000 | 4609383 | 4609383 | 0.00 | 21.51 | 24070 | 14.83 | 15.16 | 17.14 | 5936 | 33.90 | 24.50 | 27.13 |  |  |  |  |  |
| b151_GeoGS_LoD2_s0 | GeoGS | LoD2 | 0 | 1 | TRAINING_COMPLETE | 0 | 1.46 | 30000 | 2961581 | 2961581 | 0.01 | 21.47 | 24030 | 11.39 | 12.15 | 12.37 | 8654 | 27.40 | 22.05 | 23.97 |  |  |  |  |  |
| b151_GeoGS_LoD2_s0 | GeoGS | LoD2 | 1 | 1 | TRAINING_COMPLETE | 0 | 1.22 | 30000 | 2574029 | 2574029 | 0.00 | 21.52 | 24088 | 11.10 | 15.54 | 18.24 | 10392 | 28.90 | 21.84 | 23.31 |  |  |  |  |  |
| b151_GeoGS_LoD2_s0 | GeoGS | LoD2 | 2 | 1 | TRAINING_COMPLETE | 0 | 1.20 | 30000 | 2556482 | 2556482 | 0.00 | 21.52 | 24088 | 12.55 | 17.32 | 18.33 | 7610 | 53.20 | 22.08 | 22.97 |  |  |  |  |  |
| b151_GeoGS_LoD2_s0 | GeoGS | LoD2 | 3 | 1 | TRAINING_COMPLETE | 0 | 1.16 | 30000 | 4523167 | 4523167 | 0.00 | 21.52 | 24088 | 13.31 | 15.03 | 15.29 | 10091 | 52.50 | 24.61 | 27.05 |  |  |  |  |  |
| b151_CDGS_ALS_s0 | CDGS | ALS | 0 | 1 | TRAINING_COMPLETE | 0 | 0.48 | 30000 | 1512100 | 1512100 | 0.01 | 21.52 | 24088 | 11.90 | 12.63 | 14.89 | 7368 | 44.30 | 21.59 | 24.66 |  |  |  |  |  |
| b151_CDGS_ALS_s0 | CDGS | ALS | 1 | 1 | TRAINING_COMPLETE | 0 | 0.54 | 30000 | 1508658 | 1508658 | 0.01 | 21.52 | 24088 | 15.22 | 16.56 | 20.80 | 5644 | 47.30 | 21.10 | 22.14 |  |  |  |  |  |
| b151_CDGS_ALS_s0 | CDGS | ALS | 2 | 1 | TRAINING_COMPLETE | 0 | 0.50 | 30000 | 1510673 | 1510673 | 0.01 | 21.52 | 24088 | 16.98 | 18.22 | 22.81 | 7061 | 50.80 | 19.93 | 23.03 |  |  |  |  |  |
| b151_CDGS_ALS_s0 | CDGS | ALS | 3 | 1 | TRAINING_COMPLETE | 0 | 0.43 | 30000 | 1578905 | 1578905 | 0.02 | 21.52 | 24088 | 11.43 | 13.25 | 18.27 | 7466 | 49.40 | 23.28 | 25.42 |  |  |  |  |  |
| b151_CDGS_LoD2_s0 | CDGS | LoD2 | 0 | 1 | TRAINING_COMPLETE | 0 | 0.49 | 30000 | 1516520 | 1516520 | 0.01 | 21.52 | 24088 | 11.88 | 12.56 | 14.86 | 8474 | 45.70 | 21.64 | 26.16 |  |  |  |  |  |
| b151_CDGS_LoD2_s0 | CDGS | LoD2 | 1 | 1 | TRAINING_COMPLETE | 0 | 0.45 | 30000 | 1511363 | 1511363 | 0.01 | 21.52 | 24088 | 15.18 | 16.56 | 22.06 | 8469 | 61.80 | 21.35 | 24.49 |  |  |  |  |  |
| b151_CDGS_LoD2_s0 | CDGS | LoD2 | 2 | 1 | TRAINING_COMPLETE | 0 | 0.52 | 30000 | 1502581 | 1502581 | 0.01 | 21.26 | 23821 | 17.08 | 17.81 | 21.73 | 7281 | 41.70 | 21.93 | 24.31 |  |  |  |  |  |
| b151_CDGS_LoD2_s0 | CDGS | LoD2 | 3 | 1 | TRAINING_COMPLETE | 0 | 1.06 | 30000 | 1513687 | 1513687 | 0.02 | 21.52 | 24088 | 11.46 | 12.52 | 15.63 | 10740 | 30.90 | 23.81 | 25.91 |  |  |  |  |  |
