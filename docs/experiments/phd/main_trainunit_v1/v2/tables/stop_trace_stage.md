order v2 3.5 rows 3-4: values at the stop; where the recorded peak RSS rose: before the first trace row (loading of images and maps), across the save/eval iterations 7,000/15,000/30,000, elsewhere (training and densification steps; trace every 100 cannot separate them)

| group | run | status | exit_code | last_iteration | gaussians_at_stop | peak_rss_at_stop_GiB | peak_cuda_reserved_at_stop_GiB | host_available_at_guard_GiB | min_host_available_GiB | error | rss_at_first_row_GiB | first_row_iteration | rss_last_GiB | rise_across_save_eval_GiB | rise_elsewhere_GiB | steps_over_025GiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| campus30k_ALS_s0 | campus30k_ALS_s0/a1 | EXECUTION_ERROR | 137 | 4800 | 1704802 | 33.79 | 3.859 |  |  |  | 33.79 | 100 | 33.79 | 0 | 0 | [] |
| campus30k_ALS_s0 | campus30k_ALS_s0/a2 | EXECUTION_ERROR | 137 |  |  |  |  |  |  |  |  |  |  |  |  |  |
| cells_ALS_s0_cell0 | cell0/a1 | DEADLINE_STOP_SAVED | 0 | 12700 | 3454704 | 15.43 | 12.25 |  |  |  | 13.21 | 100 | 15.43 | 1.359 | 0.8606 | [[6900, 7000, 1.36], [7000, 7100, 0.86]] |
| cells_ALS_s0_cell0 | cell0/a2 | DEADLINE_STOP_SAVED | 0 | 13200 | 5919479 | 13.44 | 11.34 |  |  |  | 13.44 | 12800 | 13.44 | 0 | 0 | [] |
| cells_ALS_s0_cell0 | cell0/a3 | EXECUTION_ERROR | 1 | 13800 | 9578396 | 14.02 | 19.89 |  |  | RuntimeError: JBGS_BINNING_GUARD_STOP_BEFORE_ALLOCATION | 14.02 | 13300 | 14.02 | 0 | 0 | [] |
| cells_ALS_s0_cell0 | cell0/a4 | EXECUTION_ERROR | 1 | 13600 | 8355096 | 14.05 | 15.24 |  |  | RuntimeError: JBGS_BINNING_GUARD_STOP_BEFORE_ALLOCATION | 14.05 | 13300 | 14.05 | 0 | 0 | [] |
| cells_ALS_s0_cell1 | cell1/a1 | DEADLINE_STOP_SAVED | 0 | 5600 | 1598244 | 19.34 | 3.252 |  |  |  | 19.34 | 100 | 19.34 | 0 | 0 | [] |
| cells_ALS_s0_cell2 | cell2/a1 | HEALTH_STOP | 1 | 15000 | 5697460 | 33.06 | 11.01 |  |  | RuntimeError: FINALTRAIN_HEALTH_STOP_count_gt_3x_6000 | 22.2 | 100 | 33.06 | 10.85 | 0 | [[14900, 15000, 10.85]] |
| cells_ALS_s0_cell2 | cell2/a2 | DEADLINE_STOP_SAVED | 137 | 20600 | 5697460 | 23.04 | 10.25 |  |  |  | 23.04 | 15100 | 23.04 | 0 | 0 | [] |
| cells_ALS_s0_cell3 | cell3/a1 | DEADLINE_STOP_SAVED | 0 | 10600 | 5150794 | 21.13 | 11.36 |  |  |  | 13.68 | 100 | 21.13 | 5.74 | 1.706 | [[6900, 7000, 5.74], [7000, 7100, 1.71]] |
| cellsef_ALS_s0_cell1fix | cellsef_ALS_s0_cell1fix/a1 | HOST_GUARD_STOP | 137 | 700 | 426801 | 19.51 | 1.07 | 18.65 | 18.65 |  | 19.51 | 100 | 19.51 | 0 | 0 | [] |
| cellsef_ALS_s0_cell1fix | cellsef_ALS_s0_cell1fix/a2 | HOST_GUARD_STOP | 137 | 8900 | 2570772 | 19.71 | 5.852 | 18.8 | 18.8 |  | 19.71 | 100 | 19.71 | 0 | 0 | [] |
| cellsef_ALS_s0_cell1fix | cellsef_ALS_s0_cell1fix/a3 | HOST_GUARD_STOP | 137 | 11600 | 2875815 | 19.4 | 6.143 | 11.04 | 11.04 |  | 19.4 | 100 | 19.4 | 0 | 0 | [] |
