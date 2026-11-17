order v2 3.5 rows 1-3 every 1,000 iterations (and the last row): gaussians; share of rows with elongation <= 0.01 at the last densification (family monitor, filter runs only; pre-filter runs have no monitor); v2 runs: elongation < 0.01 / < 0.1 and current RSS / cgroup / CUDA (trace1000); peak RSS and peak CUDA reserved (jbgs_trace, running maxima)

| run | role | iteration | gaussians | needle_le_001_share_at_last_densify | last_densify_iteration | elong_lt_001 | elong_lt_01 | rss_now_GiB | cgroup_now_GiB | cuda_alloc_now_GiB | peak_rss_GiB | peak_cuda_reserved_GiB | elapsed_s | last_row | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| campus30k_ALS_s0/a1 | stopped | 1000 | 1119391 |  |  |  |  |  |  |  | 33.79 | 2.297 | 935.8 | False | EXECUTION_ERROR |
| campus30k_ALS_s0/a1 | stopped | 2000 | 1487274 |  |  |  |  |  |  |  | 33.79 | 3.193 | 1423 | False | EXECUTION_ERROR |
| campus30k_ALS_s0/a1 | stopped | 3000 | 1874827 |  |  |  |  |  |  |  | 33.79 | 3.859 | 2026 | False | EXECUTION_ERROR |
| campus30k_ALS_s0/a1 | stopped | 4000 | 1354191 |  |  |  |  |  |  |  | 33.79 | 3.859 | 2503 | False | EXECUTION_ERROR |
| campus30k_ALS_s0/a1 | stopped | 4800 | 1704802 |  |  |  |  |  |  |  | 33.79 | 3.859 | 2859 | True | EXECUTION_ERROR |
| campusef30k_ALS_s0/a2 | finished | 1000 | 1117853 | 0 | 1000 |  |  |  |  |  | 34.04 | 2.586 | 438.7 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 2000 | 1489685 | 0 | 2000 |  |  |  |  |  | 34.04 | 3.467 | 912.7 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 3000 | 1877936 | 0 | 3000 |  |  |  |  |  | 34.04 | 4.268 | 1411 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 4000 | 1357740 | 0 | 4000 |  |  |  |  |  | 34.04 | 4.465 | 1814 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 5000 | 1822963 | 0 | 5000 |  |  |  |  |  | 34.04 | 4.465 | 2262 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 6000 | 2360848 | 0 | 6000 |  |  |  |  |  | 34.04 | 5.439 | 2806 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 7000 | 1607658 | 6.358e-07 | 7000 |  |  |  |  |  | 34.04 | 5.439 | 3517 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 8000 | 2153551 | 3.349e-06 | 8000 |  |  |  |  |  | 34.04 | 5.439 | 4083 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 9000 | 2720422 | 9.359e-06 | 9000 |  |  |  |  |  | 34.04 | 6.494 | 4772 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 10000 | 1879032 | 1.848e-05 | 10000 |  |  |  |  |  | 34.04 | 6.494 | 5325 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 11000 | 2496464 | 3.751e-05 | 11000 |  |  |  |  |  | 34.04 | 6.494 | 5985 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 12000 | 3113887 | 7.193e-05 | 12000 |  |  |  |  |  | 34.04 | 6.926 | 6786 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 13000 | 2049596 | 0.0001039 | 13000 |  |  |  |  |  | 34.04 | 6.926 | 7411 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 14000 | 2764595 | 0.0002156 | 14000 |  |  |  |  |  | 34.04 | 6.926 | 8192 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 15000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.04 | 7.102 | 9340 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 16000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 9721 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 17000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.006e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 18000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.04e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 19000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.073e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 20000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.106e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 21000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.138e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 22000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.17e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 23000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.202e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 24000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.233e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 25000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.265e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 26000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.296e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 27000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.327e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 28000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.358e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 29000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.389e+04 | False | TRAINING_COMPLETE |
| campusef30k_ALS_s0/a2 | finished | 30000 | 3439948 | 0.0004674 | 14900 |  |  |  |  |  | 34.92 | 7.102 | 1.446e+04 | True | TRAINING_COMPLETE |
| cell0/a1 | stopped | 1000 | 397500 |  |  |  |  |  |  |  | 13.21 | 1.006 | 247.7 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 2000 | 715639 |  |  |  |  |  |  |  | 13.21 | 1.713 | 487.3 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 3000 | 1182824 |  |  |  |  |  |  |  | 13.21 | 2.568 | 789.8 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 4000 | 1082122 |  |  |  |  |  |  |  | 13.21 | 2.625 | 1077 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 5000 | 1599569 |  |  |  |  |  |  |  | 13.21 | 3.562 | 1456 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 6000 | 2197822 |  |  |  |  |  |  |  | 13.21 | 4.656 | 2004 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 7000 | 1783975 |  |  |  |  |  |  |  | 14.57 | 4.734 | 2702 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 8000 | 2390277 |  |  |  |  |  |  |  | 15.43 | 4.734 | 3376 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 9000 | 3018062 |  |  |  |  |  |  |  | 15.43 | 6.746 | 4214 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 10000 | 2257040 |  |  |  |  |  |  |  | 15.43 | 6.746 | 4924 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 11000 | 3239089 |  |  |  |  |  |  |  | 15.43 | 6.746 | 5797 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 12000 | 6403947 |  |  |  |  |  |  |  | 15.43 | 11.86 | 8343 | False | DEADLINE_STOP_SAVED |
| cell0/a1 | stopped | 12700 | 3454704 |  |  |  |  |  |  |  | 15.43 | 12.25 | 9457 | True | DEADLINE_STOP_SAVED |
| cell0/a2 | stopped | 13000 | 4843672 |  |  |  |  |  |  |  | 13.44 | 10.3 | 707.4 | False | DEADLINE_STOP_SAVED |
| cell0/a2 | stopped | 13200 | 5919479 |  |  |  |  |  |  |  | 13.44 | 11.34 | 1284 | True | DEADLINE_STOP_SAVED |
| cell0/a3 | stopped | 13800 | 9578396 |  |  |  |  |  |  |  | 14.02 | 19.89 | 3558 | True | EXECUTION_ERROR |
| cell0/a4 | stopped | 13600 | 8355096 |  |  |  |  |  |  |  | 14.05 | 15.24 | 2431 | True | EXECUTION_ERROR |
| cell0ef_ALS_s0/a1 | finished | 1000 | 396565 | 0 | 1000 |  |  |  |  |  | 13.29 | 1.031 | 191.2 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 2000 | 705134 | 0 | 2000 |  |  |  |  |  | 13.29 | 1.605 | 385.7 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 3000 | 1195145 | 8.773e-07 | 3000 |  |  |  |  |  | 13.29 | 2.549 | 628.2 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 4000 | 1125347 | 1.293e-05 | 4000 |  |  |  |  |  | 13.29 | 2.664 | 879.4 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 5000 | 1676210 | 6.729e-05 | 5000 |  |  |  |  |  | 13.29 | 3.738 | 1216 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 6000 | 2282801 | 0.0002766 | 6000 |  |  |  |  |  | 13.29 | 4.695 | 1682 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 7000 | 1838269 | 0.0001895 | 7000 |  |  |  |  |  | 14.98 | 4.695 | 2255 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 8000 | 2458453 | 0.0002263 | 8000 |  |  |  |  |  | 15.91 | 5.184 | 2892 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 9000 | 3063526 | 0.0003404 | 9000 |  |  |  |  |  | 15.91 | 6.18 | 3669 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 10000 | 2258190 | 0.0003337 | 10000 |  |  |  |  |  | 15.91 | 6.18 | 4260 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 11000 | 2924726 | 0.0006487 | 11000 |  |  |  |  |  | 15.91 | 6.199 | 5019 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 12000 | 3553179 | 0.001347 | 12000 |  |  |  |  |  | 15.91 | 7.391 | 5945 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 13000 | 2497617 | 0.001228 | 13000 |  |  |  |  |  | 15.91 | 8.035 | 6589 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 14000 | 3209586 | 0.002123 | 14000 |  |  |  |  |  | 15.91 | 8.035 | 7402 | False | PROBE_STOP_15000 |
| cell0ef_ALS_s0/a1 | finished | 15000 | 3819261 | 0.003491 | 14900 |  |  |  |  |  | 21.36 | 8.035 | 8478 | True | PROBE_STOP_15000 |
| cellsef_ALS_s0_cell0/a2 | finished | 16000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.688 | 432.9 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 17000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.824 | 799.5 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 18000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 1164 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 19000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 1525 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 20000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 1884 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 21000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 2243 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 22000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 2601 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 23000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 2954 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 24000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 3308 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 25000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 3659 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 26000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 4007 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 27000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 4359 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 28000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 4708 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 29000 | 3819261 |  |  |  |  |  |  |  | 13.72 | 6.902 | 5057 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell0/a2 | finished | 30000 | 3819261 |  |  |  |  |  |  |  | 21.37 | 6.902 | 5597 | True | TRAINING_COMPLETE |
| cell1/a1 | stopped | 1000 | 489141 |  |  |  |  |  |  |  | 19.34 | 1.145 | 314.6 | False | DEADLINE_STOP_SAVED |
| cell1/a1 | stopped | 2000 | 764470 |  |  |  |  |  |  |  | 19.34 | 1.715 | 559.8 | False | DEADLINE_STOP_SAVED |
| cell1/a1 | stopped | 3000 | 1120051 |  |  |  |  |  |  |  | 19.34 | 2.379 | 837.5 | False | DEADLINE_STOP_SAVED |
| cell1/a1 | stopped | 4000 | 983969 |  |  |  |  |  |  |  | 19.34 | 2.379 | 1122 | False | DEADLINE_STOP_SAVED |
| cell1/a1 | stopped | 5000 | 1344309 |  |  |  |  |  |  |  | 19.34 | 2.902 | 1528 | False | DEADLINE_STOP_SAVED |
| cell1/a1 | stopped | 5600 | 1598244 |  |  |  |  |  |  |  | 19.34 | 3.252 | 1826 | True | DEADLINE_STOP_SAVED |
| cellsef_ALS_s0_cell1/a3 | finished | 1000 | 489462 | 0 | 1000 |  |  |  |  |  | 19.28 | 1.17 | 236.3 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 2000 | 763652 | 0 | 2000 |  |  |  |  |  | 19.28 | 1.822 | 460.5 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 3000 | 1136299 | 0 | 3000 |  |  |  |  |  | 19.28 | 2.471 | 718.5 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 4000 | 1008582 | 0 | 4000 |  |  |  |  |  | 19.28 | 2.527 | 977.8 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 5000 | 1400174 | 0 | 5000 |  |  |  |  |  | 19.28 | 3.018 | 1291 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 6000 | 1854736 | 5.532e-07 | 6000 |  |  |  |  |  | 19.28 | 3.818 | 1669 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 7000 | 1444517 | 7.13e-07 | 7000 |  |  |  |  |  | 19.28 | 3.818 | 2146 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 8000 | 1921717 | 9.064e-06 | 8000 |  |  |  |  |  | 19.28 | 4.209 | 2579 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 9000 | 2398907 | 3.957e-05 | 9000 |  |  |  |  |  | 19.28 | 5.381 | 3072 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 10000 | 1820212 | 5.191e-05 | 10000 |  |  |  |  |  | 19.28 | 5.381 | 3503 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 11000 | 2355150 | 0.00013 | 11000 |  |  |  |  |  | 19.28 | 5.381 | 4011 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 12000 | 2876087 | 0.0002696 | 12000 |  |  |  |  |  | 19.28 | 5.848 | 4591 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 13000 | 2098057 | 0.0002309 | 13000 |  |  |  |  |  | 19.28 | 5.85 | 5084 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 14000 | 2654823 | 0.0005063 | 14000 |  |  |  |  |  | 19.28 | 5.85 | 5648 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 15000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 23.57 | 6.355 | 6391 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 16000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 6697 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 17000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 6974 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 18000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 7244 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 19000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 7515 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 20000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 7789 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 21000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 8059 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 22000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 8328 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 23000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 8595 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 24000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 8861 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 25000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 9126 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 26000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 9388 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 27000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 9648 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 28000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 9910 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 29000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 1.017e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 30000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 1.062e+04 | True | TRAINING_COMPLETE |
| cell2/a1 | stopped | 1000 | 511788 |  |  |  |  |  |  |  | 22.2 | 1.205 | 274.1 | False | HEALTH_STOP |
| cell2/a1 | stopped | 2000 | 772340 |  |  |  |  |  |  |  | 22.2 | 1.693 | 511.4 | False | HEALTH_STOP |
| cell2/a1 | stopped | 3000 | 1168817 |  |  |  |  |  |  |  | 22.2 | 2.434 | 775.1 | False | HEALTH_STOP |
| cell2/a1 | stopped | 4000 | 984774 |  |  |  |  |  |  |  | 22.2 | 2.49 | 1029 | False | HEALTH_STOP |
| cell2/a1 | stopped | 5000 | 1409294 |  |  |  |  |  |  |  | 22.2 | 3.018 | 1318 | False | HEALTH_STOP |
| cell2/a1 | stopped | 6000 | 1858449 |  |  |  |  |  |  |  | 22.2 | 4.094 | 1665 | False | HEALTH_STOP |
| cell2/a1 | stopped | 7000 | 1389474 |  |  |  |  |  |  |  | 22.2 | 4.094 | 2129 | False | HEALTH_STOP |
| cell2/a1 | stopped | 8000 | 1863091 |  |  |  |  |  |  |  | 22.2 | 4.094 | 2526 | False | HEALTH_STOP |
| cell2/a1 | stopped | 9000 | 2350595 |  |  |  |  |  |  |  | 22.2 | 4.99 | 2978 | False | HEALTH_STOP |
| cell2/a1 | stopped | 10000 | 1861714 |  |  |  |  |  |  |  | 22.2 | 4.99 | 3393 | False | HEALTH_STOP |
| cell2/a1 | stopped | 11000 | 2397052 |  |  |  |  |  |  |  | 22.2 | 5.012 | 3885 | False | HEALTH_STOP |
| cell2/a1 | stopped | 12000 | 3071328 |  |  |  |  |  |  |  | 22.2 | 6.242 | 4519 | False | HEALTH_STOP |
| cell2/a1 | stopped | 13000 | 2203124 |  |  |  |  |  |  |  | 22.2 | 6.242 | 5046 | False | HEALTH_STOP |
| cell2/a1 | stopped | 14000 | 3452304 |  |  |  |  |  |  |  | 22.2 | 6.963 | 5864 | False | HEALTH_STOP |
| cell2/a1 | stopped | 15000 | 5697460 |  |  |  |  |  |  |  | 33.06 | 11.01 | 7838 | True | HEALTH_STOP |
| cell2/a2 | stopped | 16000 | 5697460 |  |  |  |  |  |  |  | 23.04 | 10.09 | 1460 | False | DEADLINE_STOP_SAVED |
| cell2/a2 | stopped | 17000 | 5697460 |  |  |  |  |  |  |  | 23.04 | 10.09 | 2284 | False | DEADLINE_STOP_SAVED |
| cell2/a2 | stopped | 18000 | 5697460 |  |  |  |  |  |  |  | 23.04 | 10.25 | 3327 | False | DEADLINE_STOP_SAVED |
| cell2/a2 | stopped | 19000 | 5697460 |  |  |  |  |  |  |  | 23.04 | 10.25 | 4384 | False | DEADLINE_STOP_SAVED |
| cell2/a2 | stopped | 20000 | 5697460 |  |  |  |  |  |  |  | 23.04 | 10.25 | 5137 | False | DEADLINE_STOP_SAVED |
| cell2/a2 | stopped | 20600 | 5697460 |  |  |  |  |  |  |  | 23.04 | 10.25 | 5949 | True | DEADLINE_STOP_SAVED |
| cellsef_ALS_s0_cell2/a3 | finished | 1000 | 509773 | 0 | 1000 |  |  |  |  |  | 22.18 | 1.229 | 242.5 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 2000 | 783008 | 0 | 2000 |  |  |  |  |  | 22.18 | 1.781 | 475.4 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 3000 | 1182063 | 0 | 3000 |  |  |  |  |  | 22.18 | 2.512 | 735.1 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 4000 | 1005107 | 0 | 4000 |  |  |  |  |  | 22.18 | 3.037 | 984.9 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 5000 | 1427143 | 0 | 5000 |  |  |  |  |  | 22.18 | 3.078 | 1271 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 6000 | 1864241 | 9.892e-06 | 6000 |  |  |  |  |  | 22.18 | 4.426 | 1611 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 7000 | 1395451 | 4.578e-05 | 7000 |  |  |  |  |  | 22.18 | 4.426 | 2084 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 8000 | 1874993 | 8.577e-05 | 8000 |  |  |  |  |  | 22.18 | 4.426 | 2480 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 9000 | 2357261 | 0.0001086 | 9000 |  |  |  |  |  | 22.18 | 5.109 | 2934 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 10000 | 1876557 | 6.887e-05 | 10000 |  |  |  |  |  | 22.18 | 5.109 | 3353 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 11000 | 2401040 | 7.258e-05 | 11000 |  |  |  |  |  | 22.18 | 5.109 | 3880 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 12000 | 2923300 | 0.0001216 | 12000 |  |  |  |  |  | 22.18 | 6.533 | 4474 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 13000 | 2104446 | 9.61e-05 | 13000 |  |  |  |  |  | 22.18 | 6.533 | 4947 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 14000 | 2666159 | 0.0001486 | 14000 |  |  |  |  |  | 22.18 | 6.533 | 5510 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 15000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 24.9 | 6.533 | 6305 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 16000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 6619 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 17000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 6872 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 18000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 7131 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 19000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 7386 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 20000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 7641 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 21000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 7893 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 22000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 8142 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 23000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 8392 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 24000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 8640 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 25000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 8888 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 26000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 9134 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 27000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 9381 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 28000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 9626 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 29000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 9868 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell2/a3 | finished | 30000 | 3123569 | 0.0002179 | 14900 |  |  |  |  |  | 26.23 | 6.533 | 1.025e+04 | True | TRAINING_COMPLETE |
| cell3/a1 | stopped | 1000 | 671054 |  |  |  |  |  |  |  | 13.68 | 1.596 | 260.2 | False | DEADLINE_STOP_SAVED |
| cell3/a1 | stopped | 2000 | 1278920 |  |  |  |  |  |  |  | 13.68 | 2.705 | 587.1 | False | DEADLINE_STOP_SAVED |
| cell3/a1 | stopped | 3000 | 2088929 |  |  |  |  |  |  |  | 13.68 | 4.287 | 1051 | False | DEADLINE_STOP_SAVED |
| cell3/a1 | stopped | 4000 | 1984597 |  |  |  |  |  |  |  | 13.68 | 4.402 | 1574 | False | DEADLINE_STOP_SAVED |
| cell3/a1 | stopped | 5000 | 3022404 |  |  |  |  |  |  |  | 13.68 | 5.596 | 2304 | False | DEADLINE_STOP_SAVED |
| cell3/a1 | stopped | 6000 | 4046106 |  |  |  |  |  |  |  | 13.68 | 7.705 | 3282 | False | DEADLINE_STOP_SAVED |
| cell3/a1 | stopped | 7000 | 3193506 |  |  |  |  |  |  |  | 19.42 | 8.25 | 4354 | False | DEADLINE_STOP_SAVED |
| cell3/a1 | stopped | 8000 | 4387547 |  |  |  |  |  |  |  | 21.13 | 8.953 | 5608 | False | DEADLINE_STOP_SAVED |
| cell3/a1 | stopped | 9000 | 5666857 |  |  |  |  |  |  |  | 21.13 | 11.16 | 7085 | False | DEADLINE_STOP_SAVED |
| cell3/a1 | stopped | 10000 | 4139384 |  |  |  |  |  |  |  | 21.13 | 11.36 | 8322 | False | DEADLINE_STOP_SAVED |
| cell3/a1 | stopped | 10600 | 5150794 |  |  |  |  |  |  |  | 21.13 | 11.36 | 9268 | True | DEADLINE_STOP_SAVED |
| cellsef_ALS_s0_cell3/a2 | finished | 1000 | 670906 | 0 | 1000 |  |  |  |  |  | 13.6 | 1.525 | 249.3 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 2000 | 1277001 | 0 | 2000 |  |  |  |  |  | 13.6 | 2.607 | 575.7 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 3000 | 2074643 | 0 | 3000 |  |  |  |  |  | 13.6 | 4.092 | 1051 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 4000 | 1973059 | 0 | 4000 |  |  |  |  |  | 13.6 | 4.637 | 1567 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 5000 | 3006231 | 0 | 5000 |  |  |  |  |  | 13.6 | 6.297 | 2286 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 6000 | 4028945 | 9.408e-06 | 6000 |  |  |  |  |  | 13.6 | 7.783 | 3251 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 7000 | 3189657 | 5.097e-05 | 7000 |  |  |  |  |  | 19.46 | 8.094 | 4241 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 8000 | 4375875 | 0.0001495 | 8000 |  |  |  |  |  | 21.18 | 9.266 | 5424 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 9000 | 5582430 | 0.0003847 | 9000 |  |  |  |  |  | 21.18 | 11.43 | 6926 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 10000 | 4001324 | 0.0003137 | 10000 |  |  |  |  |  | 21.18 | 11.43 | 8074 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 11000 | 5112528 | 0.0005856 | 11000 |  |  |  |  |  | 21.18 | 11.43 | 9420 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 12000 | 6252765 | 0.00112 | 12000 |  |  |  |  |  | 21.18 | 12.25 | 1.103e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 13000 | 4449947 | 0.0007336 | 13000 |  |  |  |  |  | 21.18 | 12.25 | 1.224e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 14000 | 5468119 | 0.001433 | 14000 |  |  |  |  |  | 21.18 | 12.59 | 1.362e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 15000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 29.95 | 13.49 | 1.528e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 16000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 1.587e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 17000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 1.637e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 18000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 1.687e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 19000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 1.736e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 20000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 1.785e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 21000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 1.835e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 22000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 1.883e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 23000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 1.932e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 24000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 1.981e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 25000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 2.029e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 26000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 2.077e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 27000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 2.125e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 28000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 2.173e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 29000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 2.221e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell3/a2 | finished | 30000 | 6423189 | 0.002203 | 14900 |  |  |  |  |  | 30.61 | 13.49 | 2.286e+04 | True | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1fix/a1 | stopped | 700 | 426801 | 0 | 700 |  |  |  |  |  | 19.51 | 1.07 | 189.7 | True | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a2 | stopped | 1000 | 498410 | 0 | 1000 |  |  |  |  |  | 19.71 | 1.189 | 231.3 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a2 | stopped | 2000 | 815484 | 0 | 2000 |  |  |  |  |  | 19.71 | 1.822 | 474.1 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a2 | stopped | 3000 | 1263349 | 0 | 3000 |  |  |  |  |  | 19.71 | 2.646 | 756.5 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a2 | stopped | 4000 | 1124526 | 0 | 4000 |  |  |  |  |  | 19.71 | 2.998 | 1037 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a2 | stopped | 5000 | 1554222 | 1.313e-06 | 5000 |  |  |  |  |  | 19.71 | 3.43 | 1388 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a2 | stopped | 6000 | 2051313 | 4.997e-06 | 6000 |  |  |  |  |  | 19.71 | 4.932 | 1856 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a2 | stopped | 7000 | 1601197 | 1.286e-05 | 7000 |  |  |  |  |  | 19.71 | 4.932 | 2471 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a2 | stopped | 8000 | 2119606 | 2.174e-05 | 8000 |  |  |  |  |  | 19.71 | 4.932 | 3041 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a2 | stopped | 8900 | 2570772 | 3.561e-05 | 8900 |  |  |  |  |  | 19.71 | 5.852 | 3558 | True | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 1000 | 498759 | 0 | 1000 |  |  |  |  |  | 19.4 | 1.191 | 392.4 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 2000 | 813670 | 0 | 2000 |  |  |  |  |  | 19.4 | 1.822 | 642.6 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 3000 | 1241647 | 0 | 3000 |  |  |  |  |  | 19.4 | 2.686 | 926.4 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 4000 | 1114539 | 9.312e-07 | 4000 |  |  |  |  |  | 19.4 | 2.705 | 1211 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 5000 | 1524992 | 1.337e-06 | 5000 |  |  |  |  |  | 19.4 | 3.391 | 1538 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 6000 | 2004445 | 1.023e-06 | 6000 |  |  |  |  |  | 19.4 | 4.111 | 1936 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 7000 | 1572393 | 7.855e-06 | 7000 |  |  |  |  |  | 19.4 | 4.111 | 2479 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 8000 | 2086850 | 8.837e-06 | 8000 |  |  |  |  |  | 19.4 | 4.445 | 2992 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 9000 | 2598706 | 2.828e-05 | 9000 |  |  |  |  |  | 19.4 | 5.361 | 3525 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 10000 | 1942072 | 5.076e-05 | 10000 |  |  |  |  |  | 19.4 | 5.439 | 3983 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 11000 | 2527963 | 0.0001638 | 11000 |  |  |  |  |  | 19.4 | 5.439 | 4513 | False | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1fix/a3 | stopped | 11600 | 2875815 | 0.0003063 | 11600 |  |  |  |  |  | 19.4 | 6.143 | 4901 | True | HOST_GUARD_STOP |
| cellsef_ALS_s0_cell1/a3 | finished | 1000 | 489462 | 0 | 1000 |  |  |  |  |  | 19.28 | 1.17 | 236.3 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 2000 | 763652 | 0 | 2000 |  |  |  |  |  | 19.28 | 1.822 | 460.5 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 3000 | 1136299 | 0 | 3000 |  |  |  |  |  | 19.28 | 2.471 | 718.5 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 4000 | 1008582 | 0 | 4000 |  |  |  |  |  | 19.28 | 2.527 | 977.8 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 5000 | 1400174 | 0 | 5000 |  |  |  |  |  | 19.28 | 3.018 | 1291 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 6000 | 1854736 | 5.532e-07 | 6000 |  |  |  |  |  | 19.28 | 3.818 | 1669 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 7000 | 1444517 | 7.13e-07 | 7000 |  |  |  |  |  | 19.28 | 3.818 | 2146 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 8000 | 1921717 | 9.064e-06 | 8000 |  |  |  |  |  | 19.28 | 4.209 | 2579 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 9000 | 2398907 | 3.957e-05 | 9000 |  |  |  |  |  | 19.28 | 5.381 | 3072 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 10000 | 1820212 | 5.191e-05 | 10000 |  |  |  |  |  | 19.28 | 5.381 | 3503 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 11000 | 2355150 | 0.00013 | 11000 |  |  |  |  |  | 19.28 | 5.381 | 4011 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 12000 | 2876087 | 0.0002696 | 12000 |  |  |  |  |  | 19.28 | 5.848 | 4591 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 13000 | 2098057 | 0.0002309 | 13000 |  |  |  |  |  | 19.28 | 5.85 | 5084 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 14000 | 2654823 | 0.0005063 | 14000 |  |  |  |  |  | 19.28 | 5.85 | 5648 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 15000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 23.57 | 6.355 | 6391 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 16000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 6697 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 17000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 6974 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 18000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 7244 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 19000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 7515 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 20000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 7789 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 21000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 8059 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 22000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 8328 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 23000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 8595 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 24000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 8861 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 25000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 9126 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 26000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 9388 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 27000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 9648 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 28000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 9910 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 29000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 1.017e+04 | False | TRAINING_COMPLETE |
| cellsef_ALS_s0_cell1/a3 | finished | 30000 | 3231493 | 0.0009857 | 14900 |  |  |  |  |  | 24.99 | 6.355 | 1.062e+04 | True | TRAINING_COMPLETE |
