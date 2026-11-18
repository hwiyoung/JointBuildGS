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
| cells9ef_ALS_s0_cell1/a1 | v2 | 1000 | 243427 | 0 | 1000 | 0 | 0.0004437 | 7.937 | 8.326 | 0.3563 | 11.11 | 0.7812 | 156.7 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 2000 | 559687 | 0 | 2000 | 0 | 0.01104 | 7.941 | 8.331 | 0.7169 | 11.11 | 1.338 | 296 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 3000 | 1107591 | 0 | 3000 | 0 | 0.03206 | 7.945 | 8.336 | 1.348 | 11.11 | 2.646 | 492.6 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 4000 | 1165715 | 1.344e-05 | 4000 | 1.287e-05 | 0.05904 | 7.944 | 8.336 | 1.423 | 11.11 | 2.646 | 721.9 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 5000 | 1698190 | 5.18e-05 | 5000 | 4.77e-05 | 0.08954 | 7.947 | 8.339 | 2.042 | 11.11 | 4.15 | 1037 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 6000 | 2192549 | 9.619e-05 | 6000 | 9.213e-05 | 0.115 | 7.951 | 8.322 | 2.623 | 11.11 | 4.795 | 1471 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 7000 | 1762364 | 0.0001122 | 7000 | 0.0001072 | 0.1323 | 9.275 | 10.25 | 2.124 | 13.58 | 4.795 | 1955 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 8000 | 2272308 | 0.0001928 | 8000 | 0.0001848 | 0.1647 | 8.207 | 10.85 | 2.718 | 14.44 | 5.029 | 2452 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 9000 | 2723763 | 0.0003119 | 9000 | 0.0003022 | 0.1948 | 8.22 | 10.86 | 3.249 | 14.44 | 5.557 | 3019 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 10000 | 2089309 | 0.0002237 | 10000 | 0.000212 | 0.2001 | 8.216 | 10.85 | 2.503 | 14.44 | 5.557 | 3537 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 11000 | 2581632 | 0.0003627 | 11000 | 0.0003467 | 0.2365 | 8.224 | 10.86 | 3.08 | 14.44 | 5.557 | 4045 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 12000 | 3024756 | 0.0005462 | 12000 | 0.0005313 | 0.2669 | 8.149 | 10.79 | 3.6 | 14.44 | 6.182 | 4589 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 13000 | 2317852 | 0.0005554 | 13000 | 0.0005341 | 0.2654 | 8.152 | 10.79 | 2.772 | 14.44 | 6.182 | 5030 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 14000 | 2784296 | 0.0008099 | 14000 | 0.0007664 | 0.3006 | 8.143 | 10.78 | 3.318 | 14.44 | 6.182 | 5549 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 15000 | 3188618 | 0.001132 | 14900 | 0.001177 | 0.3299 | 10.04 | 13.71 | 3.124 | 18.14 | 6.572 | 6205 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 16000 | 3188618 | 0.001132 | 14900 | 0.001429 | 0.3335 | 8.153 | 14.81 | 3.124 | 19.52 | 6.572 | 6494 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 17000 | 3188618 | 0.001132 | 14900 | 0.001636 | 0.3372 | 8.153 | 14.82 | 3.124 | 19.52 | 6.572 | 6751 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 18000 | 3188618 | 0.001132 | 14900 | 0.001826 | 0.341 | 8.153 | 14.82 | 3.124 | 19.52 | 6.572 | 7006 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 19000 | 3188618 | 0.001132 | 14900 | 0.002031 | 0.3446 | 8.153 | 14.82 | 3.124 | 19.52 | 6.572 | 7263 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 20000 | 3188618 | 0.001132 | 14900 | 0.002262 | 0.3482 | 8.161 | 14.82 | 3.124 | 19.52 | 6.572 | 7518 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 21000 | 3188618 | 0.001132 | 14900 | 0.002483 | 0.3515 | 8.153 | 14.84 | 3.124 | 19.52 | 6.572 | 7794 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 22000 | 3188618 | 0.001132 | 14900 | 0.002751 | 0.3547 | 8.153 | 14.84 | 3.124 | 19.52 | 6.572 | 8046 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 23000 | 3188618 | 0.001132 | 14900 | 0.003043 | 0.3578 | 8.153 | 14.84 | 3.124 | 19.52 | 6.572 | 8298 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 24000 | 3188618 | 0.001132 | 14900 | 0.003337 | 0.3608 | 8.153 | 14.84 | 3.124 | 19.52 | 6.572 | 8548 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 25000 | 3188618 | 0.001132 | 14900 | 0.003661 | 0.3637 | 8.153 | 14.84 | 3.124 | 19.52 | 6.572 | 8798 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 26000 | 3188618 | 0.001132 | 14900 | 0.003967 | 0.3663 | 8.153 | 14.84 | 3.124 | 19.52 | 6.572 | 9048 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 27000 | 3188618 | 0.001132 | 14900 | 0.004355 | 0.3687 | 8.153 | 14.84 | 3.124 | 19.52 | 6.572 | 9296 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 28000 | 3188618 | 0.001132 | 14900 | 0.004743 | 0.3709 | 8.153 | 14.84 | 3.124 | 19.52 | 6.572 | 9587 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 29000 | 3188618 | 0.001132 | 14900 | 0.005176 | 0.3732 | 8.153 | 14.84 | 3.124 | 19.52 | 6.572 | 9834 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell1/a1 | v2 | 30000 | 3188618 | 0.001132 | 14900 | 0.005625 | 0.3754 | 10.06 | 17.52 | 3.124 | 19.52 | 6.572 | 1.019e+04 | True | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 1000 | 276573 | 0 | 1000 | 0 | 0 | 12.94 | 13.12 | 0.4042 | 18.76 | 0.8457 | 209.9 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 2000 | 476011 | 0 | 2000 | 0 | 0.001118 | 12.94 | 13.12 | 0.6321 | 18.76 | 1.297 | 352.4 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 3000 | 848295 | 0 | 3000 | 0 | 0.007469 | 12.94 | 13.12 | 1.055 | 18.76 | 2.006 | 508.1 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 4000 | 733395 | 1.426e-06 | 4000 | 1.364e-06 | 0.01828 | 12.94 | 13.12 | 0.9294 | 18.76 | 2.006 | 665 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 5000 | 1096795 | 6.655e-06 | 5000 | 6.382e-06 | 0.03872 | 12.94 | 13.13 | 1.348 | 18.76 | 2.445 | 839.7 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 6000 | 1496787 | 0.0001611 | 6000 | 0.000155 | 0.06694 | 12.94 | 13.13 | 1.814 | 18.76 | 3.291 | 1042 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 7000 | 1191903 | 9.026e-05 | 7000 | 8.306e-05 | 0.08398 | 13.96 | 14.62 | 1.462 | 18.76 | 3.291 | 1317 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 8000 | 1592318 | 0.0001494 | 8000 | 0.0001363 | 0.1138 | 13.2 | 14.98 | 1.927 | 18.76 | 3.369 | 1545 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 9000 | 1965527 | 0.0002685 | 9000 | 0.00026 | 0.1431 | 13.12 | 14.91 | 2.372 | 18.76 | 4.326 | 1795 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 10000 | 1460362 | 0.0002514 | 10000 | 0.0002342 | 0.1577 | 13.12 | 14.91 | 1.78 | 18.76 | 4.326 | 2011 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 11000 | 1871212 | 0.0003604 | 11000 | 0.0003431 | 0.195 | 13.12 | 14.91 | 2.259 | 18.76 | 4.326 | 2255 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 12000 | 2296367 | 0.0005701 | 12000 | 0.0005513 | 0.2313 | 13.12 | 14.91 | 2.754 | 18.76 | 4.795 | 2530 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 13000 | 1700307 | 0.0003875 | 13000 | 0.0003629 | 0.2294 | 13.12 | 14.91 | 2.054 | 18.76 | 4.795 | 2773 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 14000 | 2120560 | 0.0005239 | 14000 | 0.0005003 | 0.2706 | 13.12 | 14.91 | 2.55 | 18.76 | 4.795 | 3046 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 15000 | 2491857 | 0.0008561 | 14900 | 0.0009126 | 0.3029 | 14.67 | 17.32 | 2.463 | 20.98 | 5.4 | 3428 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 16000 | 2491857 | 0.0008561 | 14900 | 0.001044 | 0.3067 | 13.18 | 18.16 | 2.463 | 22.05 | 5.4 | 3623 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 17000 | 2491857 | 0.0008561 | 14900 | 0.001168 | 0.3106 | 13.18 | 18.16 | 2.463 | 22.05 | 5.4 | 3796 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 18000 | 2491857 | 0.0008561 | 14900 | 0.001276 | 0.3141 | 13.18 | 18.16 | 2.463 | 22.05 | 5.4 | 3972 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 19000 | 2491857 | 0.0008561 | 14900 | 0.001395 | 0.3173 | 13.18 | 18.16 | 2.463 | 22.05 | 5.4 | 4143 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 20000 | 2491857 | 0.0008561 | 14900 | 0.001521 | 0.3203 | 13.18 | 18.16 | 2.463 | 22.05 | 5.4 | 4318 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 21000 | 2491857 | 0.0008561 | 14900 | 0.001666 | 0.3233 | 13.18 | 18.16 | 2.463 | 22.05 | 5.4 | 4495 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 22000 | 2491857 | 0.0008561 | 14900 | 0.001808 | 0.3262 | 13.18 | 18.17 | 2.463 | 22.05 | 5.4 | 4667 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 23000 | 2491857 | 0.0008561 | 14900 | 0.001954 | 0.329 | 13.18 | 18.17 | 2.463 | 22.05 | 5.4 | 4835 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 24000 | 2491857 | 0.0008561 | 14900 | 0.002126 | 0.3316 | 13.18 | 18.17 | 2.463 | 22.05 | 5.4 | 5003 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 25000 | 2491857 | 0.0008561 | 14900 | 0.002297 | 0.3339 | 13.18 | 18.17 | 2.463 | 22.05 | 5.4 | 5170 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 26000 | 2491857 | 0.0008561 | 14900 | 0.002496 | 0.336 | 13.18 | 18.17 | 2.463 | 22.05 | 5.4 | 5337 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 27000 | 2491857 | 0.0008561 | 14900 | 0.002676 | 0.3379 | 13.18 | 18.17 | 2.463 | 22.05 | 5.4 | 5502 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 28000 | 2491857 | 0.0008561 | 14900 | 0.002907 | 0.3398 | 13.18 | 18.17 | 2.463 | 22.05 | 5.4 | 5666 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 29000 | 2491857 | 0.0008561 | 14900 | 0.003116 | 0.3417 | 13.18 | 18.17 | 2.463 | 22.05 | 5.4 | 5829 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell4/a1 | v2 | 30000 | 2491857 | 0.0008561 | 14900 | 0.00335 | 0.3432 | 14.64 | 20.5 | 2.463 | 22.05 | 5.4 | 6092 | True | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a1 | v2 | 1000 | 362281 | 0 | 1000 | 0 | 0.000276 | 6.61 | 6.984 | 0.4923 | 8.926 | 0.9727 | 153.6 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a1 | v2 | 2000 | 816904 | 0 | 2000 | 0 | 0.007636 | 6.599 | 6.973 | 1.014 | 8.926 | 1.881 | 358.7 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a1 | v2 | 3000 | 1464253 | 0 | 3000 | 0 | 0.02625 | 6.62 | 6.995 | 1.762 | 8.926 | 3.174 | 673.3 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a1 | v2 | 4000 | 1518177 | 0 | 4000 | 0 | 0.04308 | 6.621 | 6.996 | 1.83 | 8.926 | 3.582 | 1028 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a1 | v2 | 5000 | 2261148 | 9.16e-07 | 5000 | 4.423e-07 | 0.06494 | 6.619 | 6.993 | 2.694 | 8.926 | 4.365 | 1496 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a1 | v2 | 6000 | 3081256 | 1.932e-05 | 6000 | 1.85e-05 | 0.08641 | 6.62 | 6.994 | 3.652 | 8.926 | 5.965 | 2076 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a1 | v2 | 7000 | 2544650 | 3.118e-05 | 7000 | 2.476e-05 | 0.1056 | 8.259 | 9.708 | 3.027 | 14.55 | 6.258 | 2698 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a1 | v2 | 8000 | 3369295 | 7.903e-05 | 8000 | 7.183e-05 | 0.1322 | 6.842 | 10.69 | 3.989 | 15.72 | 6.807 | 3342 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a1 | v2 | 9000 | 4243059 | 0.0001956 | 9000 | 0.0001855 | 0.1586 | 6.853 | 10.7 | 5.01 | 15.72 | 8.271 | 4048 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a1 | v2 | 10000 | 3305039 | 0.0001597 | 10000 | 0.0001486 | 0.1711 | 6.857 | 10.71 | 3.913 | 15.72 | 8.74 | 4690 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a1 | v2 | 11000 | 4134690 | 0.0003346 | 11000 | 0.0003103 | 0.2069 | 6.888 | 10.75 | 4.885 | 15.72 | 8.74 | 5409 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a1 | v2 | 11800 | 4781287 | 0.0005854 | 11800 |  |  |  |  |  | 15.72 | 8.955 | 6042 | True | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell5/a2 | v2 | 1000 | 362594 | 0 | 1000 | 0 | 0.0002482 | 6.603 | 6.9 | 0.4928 | 8.836 | 0.9121 | 150.5 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 2000 | 810465 | 0 | 2000 | 0 | 0.007784 | 6.605 | 6.902 | 1.007 | 8.836 | 1.939 | 348.4 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 3000 | 1463444 | 3.619e-06 | 3000 | 3.417e-06 | 0.02558 | 6.623 | 6.921 | 1.759 | 8.836 | 3.016 | 650.9 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 4000 | 1504200 | 3.479e-06 | 4000 | 2.659e-06 | 0.04266 | 6.624 | 6.922 | 1.813 | 8.836 | 3.408 | 996.5 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 5000 | 2244208 | 2.306e-06 | 5000 | 2.228e-06 | 0.06499 | 6.621 | 6.92 | 2.675 | 8.836 | 4.443 | 1450 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 6000 | 3052517 | 2.354e-06 | 6000 | 2.293e-06 | 0.08677 | 6.626 | 6.925 | 3.619 | 8.836 | 5.908 | 2013 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 7000 | 2532980 | 5.292e-06 | 7000 | 4.738e-06 | 0.1085 | 8.284 | 9.373 | 3.012 | 14.54 | 6.904 | 2624 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 8000 | 3356803 | 7.014e-06 | 8000 | 6.256e-06 | 0.1348 | 6.884 | 10.35 | 3.975 | 15.63 | 6.904 | 3266 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 9000 | 4210690 | 9.923e-06 | 9000 | 9.025e-06 | 0.1599 | 6.886 | 10.36 | 4.974 | 15.63 | 7.998 | 3977 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 10000 | 3282106 | 1.874e-05 | 10000 | 1.828e-05 | 0.1738 | 6.889 | 10.36 | 3.886 | 15.63 | 8.018 | 4618 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 11000 | 4093882 | 6.746e-05 | 11000 | 6.351e-05 | 0.2081 | 6.862 | 10.33 | 4.838 | 15.63 | 8.797 | 5325 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 12000 | 4874084 | 0.0002503 | 12000 | 0.0002405 | 0.2399 | 6.87 | 10.36 | 5.745 | 15.63 | 9.988 | 6116 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 13000 | 3658115 | 0.0002279 | 13000 | 0.0002086 | 0.2413 | 6.887 | 10.38 | 4.33 | 15.63 | 9.988 | 6808 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 14000 | 4409977 | 0.0005586 | 14000 | 0.000542 | 0.2825 | 6.868 | 10.36 | 5.204 | 15.63 | 9.988 | 7556 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 15000 | 5071914 | 0.001267 | 14900 | 0.001381 | 0.3182 | 9.46 | 14.51 | 4.923 | 22.59 | 10.11 | 8427 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 16000 | 5071914 | 0.001267 | 14900 | 0.001549 | 0.322 | 6.848 | 15.06 | 4.923 | 22.68 | 10.11 | 8808 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 17000 | 5071914 | 0.001267 | 14900 | 0.001658 | 0.3263 | 6.848 | 15.06 | 4.923 | 22.68 | 10.11 | 9120 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 18000 | 5071914 | 0.001267 | 14900 | 0.001762 | 0.331 | 6.849 | 15.06 | 4.923 | 22.68 | 10.11 | 9434 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 19000 | 5071914 | 0.001267 | 14900 | 0.001866 | 0.336 | 6.848 | 14.73 | 4.923 | 22.68 | 10.11 | 9757 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 20000 | 5071914 | 0.001267 | 14900 | 0.001993 | 0.3408 | 6.848 | 14.4 | 4.923 | 22.68 | 10.11 | 1.008e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 21000 | 5071914 | 0.001267 | 14900 | 0.002128 | 0.3458 | 6.848 | 11 | 4.923 | 22.68 | 10.11 | 1.041e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 22000 | 5071914 | 0.001267 | 14900 | 0.002292 | 0.3508 | 6.848 | 6.558 | 4.923 | 22.68 | 10.11 | 1.084e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 23000 | 5071914 | 0.001267 | 14900 | 0.002471 | 0.3558 | 6.846 | 6.558 | 4.923 | 22.68 | 10.11 | 1.14e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 24000 | 5071914 | 0.001267 | 14900 | 0.002669 | 0.361 | 6.847 | 6.559 | 4.923 | 22.68 | 10.11 | 1.18e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 25000 | 5071914 | 0.001267 | 14900 | 0.002915 | 0.3662 | 6.847 | 6.56 | 4.923 | 22.68 | 10.11 | 1.212e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 26000 | 5071914 | 0.001267 | 14900 | 0.003188 | 0.3715 | 6.847 | 6.56 | 4.923 | 22.68 | 10.11 | 1.243e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 27000 | 5071914 | 0.001267 | 14900 | 0.003505 | 0.3765 | 6.847 | 6.561 | 4.923 | 22.68 | 10.11 | 1.276e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 28000 | 5071914 | 0.001267 | 14900 | 0.003834 | 0.3817 | 6.847 | 6.561 | 4.923 | 22.68 | 10.11 | 1.306e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 29000 | 5071914 | 0.001267 | 14900 | 0.004209 | 0.3865 | 6.847 | 6.562 | 4.923 | 22.68 | 10.11 | 1.337e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell5/a2 | v2 | 30000 | 5071914 | 0.001267 | 14900 | 0.004626 | 0.3912 | 9.761 | 11.23 | 4.923 | 22.68 | 10.11 | 1.377e+04 | True | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 1000 | 178284 | 0 | 1000 | 0 | 0 | 6.825 | 7.018 | 0.2852 | 9.284 | 0.6582 | 143.8 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 2000 | 365079 | 0 | 2000 | 0 | 0.001046 | 6.822 | 7.015 | 0.4954 | 9.284 | 0.9824 | 256.1 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 3000 | 714468 | 1.494e-06 | 3000 | 1.4e-06 | 0.01307 | 6.823 | 7.016 | 0.8959 | 9.284 | 1.555 | 381.5 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 4000 | 716729 | 1.604e-05 | 4000 | 1.395e-05 | 0.02168 | 6.825 | 7.018 | 0.9055 | 9.284 | 1.617 | 511.4 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 5000 | 1037534 | 4.454e-05 | 5000 | 4.144e-05 | 0.04299 | 6.824 | 6.915 | 1.282 | 9.284 | 2.205 | 659.7 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 6000 | 1371554 | 0.000215 | 6000 | 0.00021 | 0.07333 | 6.823 | 6.752 | 1.671 | 9.284 | 3.379 | 831.1 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 7000 | 1098119 | 8.736e-05 | 7000 | 8.196e-05 | 0.09181 | 7.765 | 8.07 | 1.35 | 10.42 | 3.379 | 1067 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 8000 | 1417957 | 0.0001106 | 8000 | 9.873e-05 | 0.1185 | 7.028 | 8.331 | 1.724 | 10.92 | 3.379 | 1276 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 9000 | 1731788 | 0.000167 | 9000 | 0.0001588 | 0.1458 | 7.028 | 7.484 | 2.09 | 10.92 | 3.645 | 1487 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 10000 | 1359448 | 0.0001293 | 10000 | 0.0001199 | 0.1552 | 7.028 | 6.772 | 1.654 | 10.92 | 3.645 | 1687 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 11000 | 1674980 | 0.0001955 | 11000 | 0.0001863 | 0.1888 | 7.027 | 6.766 | 2.03 | 10.92 | 3.645 | 1901 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 12000 | 1973798 | 0.000286 | 12000 | 0.0002705 | 0.2201 | 7.028 | 6.7 | 2.377 | 10.92 | 4.25 | 2133 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 13000 | 1514348 | 0.0004878 | 13000 | 0.0004411 | 0.231 | 7.031 | 6.703 | 1.835 | 10.92 | 4.25 | 2336 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 14000 | 1854442 | 0.0007316 | 14000 | 0.0006838 | 0.2693 | 7.028 | 6.701 | 2.241 | 10.92 | 4.25 | 2564 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 15000 | 2148219 | 0.00105 | 14900 | 0.001031 | 0.3004 | 8.338 | 8.949 | 2.131 | 13.75 | 4.543 | 2887 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 16000 | 2148219 | 0.00105 | 14900 | 0.001343 | 0.3042 | 7.058 | 9.689 | 2.131 | 14.62 | 4.543 | 3064 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 17000 | 2148219 | 0.00105 | 14900 | 0.001545 | 0.3084 | 7.058 | 9.689 | 2.131 | 14.62 | 4.543 | 3220 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 18000 | 2148219 | 0.00105 | 14900 | 0.001756 | 0.3121 | 7.052 | 8.646 | 2.131 | 14.62 | 4.543 | 3377 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 19000 | 2148219 | 0.00105 | 14900 | 0.001968 | 0.3158 | 7.052 | 8.647 | 2.131 | 14.62 | 4.543 | 3536 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 20000 | 2148219 | 0.00105 | 14900 | 0.002206 | 0.3191 | 7.053 | 8.648 | 2.131 | 14.62 | 4.543 | 3692 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 21000 | 2148219 | 0.00105 | 14900 | 0.002456 | 0.3228 | 7.053 | 8.648 | 2.131 | 14.62 | 4.543 | 3848 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 22000 | 2148219 | 0.00105 | 14900 | 0.002754 | 0.326 | 7.053 | 8.649 | 2.131 | 14.62 | 4.543 | 3994 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 23000 | 2148219 | 0.00105 | 14900 | 0.003024 | 0.329 | 7.052 | 8.647 | 2.131 | 14.62 | 4.543 | 4140 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 24000 | 2148219 | 0.00105 | 14900 | 0.003363 | 0.3321 | 7.052 | 8.648 | 2.131 | 14.62 | 4.543 | 4283 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 25000 | 2148219 | 0.00105 | 14900 | 0.0037 | 0.335 | 7.053 | 8.648 | 2.131 | 14.62 | 4.543 | 4430 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 26000 | 2148219 | 0.00105 | 14900 | 0.004086 | 0.3378 | 7.053 | 8.648 | 2.131 | 14.62 | 4.543 | 4572 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 27000 | 2148219 | 0.00105 | 14900 | 0.004452 | 0.3404 | 7.053 | 8.648 | 2.131 | 14.62 | 4.543 | 4715 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 28000 | 2148219 | 0.00105 | 14900 | 0.004864 | 0.3428 | 7.061 | 8.65 | 2.131 | 14.62 | 4.543 | 4861 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 29000 | 2148219 | 0.00105 | 14900 | 0.005294 | 0.3454 | 7.01 | 8.435 | 2.131 | 14.62 | 4.543 | 5003 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell6/a1 | v2 | 30000 | 2148219 | 0.00105 | 14900 | 0.005761 | 0.3475 | 8.28 | 9.785 | 2.131 | 14.62 | 4.543 | 5229 | True | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 1000 | 262772 | 0 | 1000 | 0 | 0.000685 | 7.231 | 7.545 | 0.3818 | 9.983 | 0.7891 | 166.2 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 2000 | 538495 | 0 | 2000 | 0 | 0.007898 | 7.234 | 7.548 | 0.6989 | 9.983 | 1.336 | 305.7 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 3000 | 923385 | 0 | 3000 | 0 | 0.02487 | 7.236 | 7.551 | 1.142 | 9.983 | 2.02 | 487.6 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 4000 | 859732 | 0 | 4000 | 0 | 0.04234 | 7.237 | 7.552 | 1.072 | 9.983 | 2.02 | 685.2 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 5000 | 1218485 | 0 | 5000 | 0 | 0.06608 | 7.247 | 7.563 | 1.494 | 9.983 | 2.998 | 923.4 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 6000 | 1613977 | 6.377e-07 | 6000 | 6.196e-07 | 0.09025 | 7.258 | 7.575 | 1.95 | 9.983 | 3.232 | 1207 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 7000 | 1266925 | 3.25e-06 | 7000 | 3.157e-06 | 0.1099 | 8.296 | 9.062 | 1.549 | 11.37 | 3.369 | 1537 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 8000 | 1686708 | 5.503e-06 | 8000 | 4.15e-06 | 0.1405 | 7.465 | 9.425 | 2.032 | 11.95 | 3.506 | 1846 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 9000 | 2084900 | 2.334e-05 | 9000 | 2.254e-05 | 0.1667 | 7.464 | 9.424 | 2.509 | 11.95 | 4.834 | 2184 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 10000 | 1631161 | 1.709e-05 | 10000 | 1.655e-05 | 0.1868 | 7.471 | 9.433 | 1.968 | 11.95 | 4.834 | 2486 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 11000 | 2032592 | 4.557e-05 | 11000 | 4.133e-05 | 0.2185 | 7.476 | 9.377 | 2.445 | 11.95 | 4.834 | 2815 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 12000 | 2395929 | 0.0001033 | 12000 | 9.725e-05 | 0.2431 | 7.476 | 8.951 | 2.88 | 11.95 | 4.834 | 3177 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 13000 | 1965062 | 8.784e-05 | 13000 | 8.244e-05 | 0.2519 | 7.476 | 8.841 | 2.369 | 11.95 | 4.834 | 3512 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 14000 | 2333329 | 0.0001847 | 14000 | 0.0001744 | 0.28 | 7.469 | 8.834 | 2.798 | 11.95 | 5.068 | 3872 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 15000 | 2634615 | 0.0003338 | 14900 | 0.0003519 | 0.3025 | 9.064 | 11.33 | 2.597 | 15.75 | 5.596 | 4334 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 16000 | 2634615 | 0.0003338 | 14900 | 0.0004392 | 0.308 | 7.505 | 12.24 | 2.597 | 16.88 | 5.596 | 4553 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 17000 | 2634615 | 0.0003338 | 14900 | 0.0005025 | 0.3136 | 7.505 | 12.24 | 2.597 | 16.88 | 5.596 | 4738 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 18000 | 2634615 | 0.0003338 | 14900 | 0.0005621 | 0.3189 | 7.506 | 12.24 | 2.597 | 16.88 | 5.596 | 4923 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 19000 | 2634615 | 0.0003338 | 14900 | 0.0006502 | 0.3241 | 7.505 | 12.24 | 2.597 | 16.88 | 5.596 | 5108 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 20000 | 2634615 | 0.0003338 | 14900 | 0.0007394 | 0.329 | 7.505 | 12.25 | 2.597 | 16.88 | 5.596 | 5293 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 21000 | 2634615 | 0.0003338 | 14900 | 0.0008445 | 0.3339 | 7.505 | 12.25 | 2.597 | 16.88 | 5.596 | 5477 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 22000 | 2634615 | 0.0003338 | 14900 | 0.0009755 | 0.3385 | 7.505 | 12.25 | 2.597 | 16.88 | 5.596 | 5659 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 23000 | 2634615 | 0.0003338 | 14900 | 0.001136 | 0.3431 | 7.505 | 12.25 | 2.597 | 16.88 | 5.596 | 5843 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 24000 | 2634615 | 0.0003338 | 14900 | 0.001305 | 0.3472 | 7.506 | 12.25 | 2.597 | 16.88 | 5.596 | 6028 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 25000 | 2634615 | 0.0003338 | 14900 | 0.001506 | 0.3517 | 7.428 | 12.16 | 2.597 | 16.88 | 5.596 | 6210 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 26000 | 2634615 | 0.0003338 | 14900 | 0.001741 | 0.3556 | 7.428 | 12.16 | 2.597 | 16.88 | 5.596 | 6389 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 27000 | 2634615 | 0.0003338 | 14900 | 0.002017 | 0.3593 | 7.428 | 12.16 | 2.597 | 16.88 | 5.596 | 6568 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 28000 | 2634615 | 0.0003338 | 14900 | 0.002317 | 0.3631 | 7.428 | 12.16 | 2.597 | 16.88 | 5.596 | 6749 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 29000 | 2634615 | 0.0003338 | 14900 | 0.002675 | 0.367 | 7.428 | 12.17 | 2.597 | 16.88 | 5.596 | 6932 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell7/a1 | v2 | 30000 | 2634615 | 0.0003338 | 14900 | 0.003049 | 0.3703 | 9.118 | 14.74 | 2.597 | 16.88 | 5.596 | 7212 | True | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a1 | v2 | 1000 | 481642 | 0 | 1000 | 0 | 0.0006166 | 6.887 | 6.671 | 0.6294 | 9.549 | 1.092 | 190.7 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell8/a1 | v2 | 2000 | 1107286 | 0 | 2000 | 0 | 0.008991 | 6.882 | 6.666 | 1.353 | 9.549 | 2.43 | 455 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell8/a1 | v2 | 3000 | 2032774 | 5.187e-07 | 3000 | 4.919e-07 | 0.02521 | 6.898 | 6.683 | 2.418 | 9.549 | 4.109 | 855.2 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell8/a1 | v2 | 4000 | 2120512 | 9.968e-07 | 4000 | 9.432e-07 | 0.04726 | 6.895 | 6.68 | 2.516 | 9.549 | 4.48 | 1305 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell8/a1 | v2 | 5000 | 3281411 | 1.149e-05 | 5000 | 1.067e-05 | 0.08566 | 6.907 | 6.635 | 3.858 | 9.549 | 6.16 | 1976 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell8/a1 | v2 | 6000 | 4527586 | 6.43e-05 | 6000 | 6.052e-05 | 0.1217 | 6.947 | 6.675 | 5.326 | 9.549 | 8.465 | 2914 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell8/a1 | v2 | 7000 | 3686531 | 7.934e-05 | 7000 | 7.378e-05 | 0.1413 | 9.108 | 10.21 | 4.345 | 18.25 | 8.695 | 3846 | False | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell8/a1 | v2 | 8000 | 4792638 | 0.0001116 | 8000 | 0.0001037 | 0.1725 | 7.144 | 10.73 | 5.64 | 19.33 | 8.992 | 4915 | True | GPU_MEMORY_STOP |
| cells9ef_ALS_s0_cell8/a2 | v2 | 1000 | 481822 | 0 | 1000 | 0 | 0.0006019 | 6.903 | 7.189 | 0.6295 | 9.391 | 1.092 | 173 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 2000 | 1106060 | 0 | 2000 | 0 | 0.008792 | 6.886 | 7.174 | 1.352 | 9.391 | 2.193 | 435.3 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 3000 | 2034734 | 0 | 3000 | 0 | 0.02544 | 6.899 | 7.187 | 2.42 | 9.391 | 4.07 | 829.1 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 4000 | 2109926 | 2.506e-06 | 4000 | 1.896e-06 | 0.04648 | 6.902 | 7.191 | 2.503 | 9.391 | 4.246 | 1266 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 5000 | 3263484 | 2.245e-05 | 5000 | 1.992e-05 | 0.0836 | 6.913 | 7.202 | 3.838 | 9.391 | 6.531 | 1904 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 6000 | 4511372 | 8.095e-05 | 6000 | 7.736e-05 | 0.1201 | 6.951 | 7.241 | 5.307 | 9.391 | 9.832 | 2809 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 7000 | 3662149 | 8.382e-05 | 7000 | 7.919e-05 | 0.1382 | 9.136 | 10.55 | 4.317 | 18.23 | 9.988 | 3691 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 8000 | 4754302 | 0.0001095 | 8000 | 0.0001054 | 0.1684 | 7.227 | 11.66 | 5.595 | 19.18 | 9.988 | 4709 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 9000 | 5829158 | 0.0001747 | 9000 | 0.0001683 | 0.1898 | 7.181 | 10.67 | 6.858 | 19.18 | 11.41 | 5912 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 10000 | 4440331 | 0.0001541 | 10000 | 0.0001468 | 0.1898 | 7.165 | 10.66 | 5.246 | 19.18 | 11.77 | 6863 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 11000 | 5511815 | 0.0002906 | 11000 | 0.0002769 | 0.2206 | 7.176 | 10.66 | 6.471 | 19.18 | 11.92 | 7950 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 12000 | 6442353 | 0.0006374 | 12000 | 0.0006214 | 0.2484 | 7.15 | 10.63 | 7.575 | 19.18 | 12.84 | 9205 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 13000 | 4929615 | 0.0004382 | 13000 | 0.0004142 | 0.24 | 7.197 | 10.68 | 5.814 | 19.18 | 12.84 | 1.02e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 14000 | 5786506 | 0.0009685 | 14000 | 0.0009434 | 0.2792 | 7.127 | 10.61 | 6.813 | 19.18 | 12.84 | 1.13e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 15000 | 6515841 | 0.001828 | 14900 | 0.001913 | 0.3133 | 10.56 | 14.35 | 6.304 | 27.41 | 13.45 | 1.263e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 16000 | 6515841 | 0.001828 | 14900 | 0.002185 | 0.3177 | 7.202 | 14.8 | 6.304 | 27.53 | 13.45 | 1.316e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 17000 | 6515841 | 0.001828 | 14900 | 0.00229 | 0.3225 | 7.203 | 14.8 | 6.304 | 27.53 | 13.45 | 1.358e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 18000 | 6515841 | 0.001828 | 14900 | 0.002404 | 0.3276 | 7.126 | 14.72 | 6.304 | 27.53 | 13.45 | 1.399e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 19000 | 6515841 | 0.001828 | 14900 | 0.002521 | 0.3329 | 7.126 | 14.72 | 6.304 | 27.53 | 13.45 | 1.44e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 20000 | 6515841 | 0.001828 | 14900 | 0.002644 | 0.338 | 7.126 | 14.72 | 6.304 | 27.53 | 13.45 | 1.481e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 21000 | 6515841 | 0.001828 | 14900 | 0.002792 | 0.3435 | 7.126 | 14.73 | 6.304 | 27.53 | 13.45 | 1.522e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 22000 | 6515841 | 0.001828 | 14900 | 0.002943 | 0.349 | 7.126 | 14.73 | 6.304 | 27.53 | 13.45 | 1.563e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 23000 | 6515841 | 0.001828 | 14900 | 0.003118 | 0.3544 | 7.126 | 14.73 | 6.304 | 27.53 | 13.45 | 1.604e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 24000 | 6515841 | 0.001828 | 14900 | 0.003323 | 0.3602 | 7.126 | 14.73 | 6.304 | 27.53 | 13.45 | 1.644e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 25000 | 6515841 | 0.001828 | 14900 | 0.00356 | 0.3659 | 7.128 | 14.75 | 6.304 | 27.53 | 13.45 | 1.685e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 26000 | 6515841 | 0.001828 | 14900 | 0.003818 | 0.3715 | 7.126 | 14.75 | 6.304 | 27.53 | 13.45 | 1.726e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 27000 | 6515841 | 0.001828 | 14900 | 0.004133 | 0.3771 | 7.126 | 14.75 | 6.304 | 27.53 | 13.45 | 1.767e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 28000 | 6515841 | 0.001828 | 14900 | 0.004455 | 0.3822 | 7.126 | 14.75 | 6.304 | 27.53 | 13.45 | 1.808e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 29000 | 6515841 | 0.001828 | 14900 | 0.004824 | 0.3874 | 7.126 | 14.75 | 6.304 | 27.53 | 13.45 | 1.848e+04 | False | TRAINING_COMPLETE |
| cells9ef_ALS_s0_cell8/a2 | v2 | 30000 | 6515841 | 0.001828 | 14900 | 0.005218 | 0.3924 | 10.63 | 18.95 | 6.304 | 27.53 | 13.45 | 1.906e+04 | True | TRAINING_COMPLETE |
