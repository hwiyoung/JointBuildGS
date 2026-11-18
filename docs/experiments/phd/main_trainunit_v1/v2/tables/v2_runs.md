order v2 5.1: per run: status, hours of the attempt with the result (넷 cell 0 includes cell0ef to 15,000) and of all attempts, gaussians final/max, GPU reserved max, host RSS max, s/iteration 100->500 of the first attempt from 0, PSNR train (5 views) / test at 30,000

| plan | prior | run | status | attempts | hours_result | hours_all_attempts | final_gaussians | max_gaussians | peak_gpu_reserved_GiB | peak_host_rss_GiB | sec_per_iter_100_500 | psnr_train | psnr_test | train_images |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 건물단위_s0 | ALS | B0ef_ALS_s0 | TRAINING_COMPLETE | 1 | 1.189 | 1.189 | 2337827 | 2337827 | 5.426 | 16.12 | 0.04629 | 23.99 | 22.68 | 243 |
| 건물단위_s1 | ALS | B0ef_ALS_s1 | TRAINING_COMPLETE | 1 | 1.132 | 1.132 | 2138422 | 2138422 | 4.41 | 15.41 | 0.04575 | 24.94 | 22.75 | 243 |
| 건물단위_s0 | ALS | R1repef_ALS_s0 | TRAINING_COMPLETE | 1 | 1.169 | 1.169 | 2245016 | 2245016 | 5.174 | 18.06 | 0.06738 | 22.49 | 23.17 | 333 |
| 건물단위_s1 | ALS | R1repef_ALS_s1 | TRAINING_COMPLETE | 1 | 1.65 | 1.65 | 2279514 | 2279514 | 4.527 | 18.21 | 0.1046 | 24.03 | 22.66 | 333 |
| 건물단위_s0 | ALS | B173nbef_ALS_s0 | TRAINING_COMPLETE | 1 | 1.456 | 1.456 | 2721464 | 2721464 | 5.271 | 16.4 | 0.04604 | 25.79 | 23.19 | 203 |
| 건물단위_s1 | ALS | B173nbef_ALS_s1 | TRAINING_COMPLETE | 1 | 1.345 | 1.345 | 2738010 | 2738010 | 6.287 | 16.42 | 0.04941 | 26.01 | 23.24 | 203 |
| 건물단위_s0 | LoD2 | B0ef_LoD2_s0 | 결과 없음(학습 안 함: 사용자 결정 2026-11-17, LoD2 기준 = 기존 필터 없음 판 FINALTRAIN_30000·seed1_s1) |  |  |  |  |  |  |  |  |  |  | 243 |
| 건물단위_s1 | LoD2 | B0ef_LoD2_s1 | 결과 없음(학습 안 함: 사용자 결정 2026-11-17, LoD2 기준 = 기존 필터 없음 판 FINALTRAIN_30000·seed1_s1) |  |  |  |  |  |  |  |  |  |  | 243 |
| 건물단위_s0 | LoD2 | R1repef_LoD2_s0 | 결과 없음(학습 안 함: 사용자 결정 2026-11-17, LoD2 기준 = 기존 필터 없음 판 FINALTRAIN_30000·seed1_s1) |  |  |  |  |  |  |  |  |  |  | 333 |
| 건물단위_s1 | LoD2 | R1repef_LoD2_s1 | 결과 없음(학습 안 함: 사용자 결정 2026-11-17, LoD2 기준 = 기존 필터 없음 판 FINALTRAIN_30000·seed1_s1) |  |  |  |  |  |  |  |  |  |  | 333 |
| 건물단위_s0 | LoD2 | B173nbef_LoD2_s0 | 결과 없음(학습 안 함: 사용자 결정 2026-11-17, LoD2 기준 = 기존 필터 없음 판 FINALTRAIN_30000·seed1_s1) |  |  |  |  |  |  |  |  |  |  | 203 |
| 건물단위_s1 | LoD2 | B173nbef_LoD2_s1 | 결과 없음(학습 안 함: 사용자 결정 2026-11-17, LoD2 기준 = 기존 필터 없음 판 FINALTRAIN_30000·seed1_s1) |  |  |  |  |  |  |  |  |  |  | 203 |
| 전체 | ALS | campusef30k_ALS_s0 | TRAINING_COMPLETE | 2 | 4.033 | 4.591 | 3439948 | 3439948 | 7.102 | 34.92 | 0.1723 | 23.65 | 21.84 | 819 |
| 넷 | ALS | cellsef_ALS_s0_cell0 | TRAINING_COMPLETE | 2 | 3.975 | 4.259 | 3819261 | 3819261 | 8.035 | 21.37 |  | 24.79 | 22.54 | 308 |
| 넷 | ALS | cellsef_ALS_s0_cell1 | TRAINING_COMPLETE | 3 | 2.967 | 3.73 | 3231493 | 3231493 | 6.355 | 24.99 | 0.1142 | 24.2 | 22.18 | 471 |
| 넷 | ALS | cellsef_ALS_s0_cell2 | TRAINING_COMPLETE | 3 | 2.858 | 4.233 | 3123569 | 3123569 | 6.533 | 26.23 | 0.1363 | 24.08 | 22.33 | 544 |
| 넷 | ALS | cellsef_ALS_s0_cell3 | TRAINING_COMPLETE | 2 | 6.378 | 8.729 | 6423189 | 6423189 | 13.49 | 30.61 | 0.118 | 27.8 | 24.9 | 324 |
| 아홉 | ALS | cells9ef_ALS_s0_cell0 | 결과 없음(학습 안 함: 평가 상자 밖, 사용자 결정 2026-11-17) |  |  |  |  |  |  |  |  |  |  | 198 |
| 아홉 | ALS | cells9ef_ALS_s0_cell1 | TRAINING_COMPLETE | 1 | 2.843 | 2.843 | 3188618 | 3188618 | 6.572 | 19.52 | 0.09386 | 24.15 | 21.95 | 259 |
| 아홉 | ALS | cells9ef_ALS_s0_cell2 | 결과 없음(학습 안 함: 평가 상자 밖, 사용자 결정 2026-11-17) |  |  |  |  |  |  |  |  |  |  | 186 |
| 아홉 | ALS | cells9ef_ALS_s0_cell3 | 결과 없음(학습 안 함: 평가 상자 밖, 사용자 결정 2026-11-17) |  |  |  |  |  |  |  |  |  |  | 201 |
| 아홉 | ALS | cells9ef_ALS_s0_cell4 | TRAINING_COMPLETE | 1 | 1.706 | 1.706 | 2491857 | 2491857 | 5.4 | 22.05 | 0.1179 | 25.1 | 22.27 | 466 |
| 아홉 | ALS | cells9ef_ALS_s0_cell5 | TRAINING_COMPLETE | 2 | 3.839 | 5.519 | 5071914 | 5071914 | 10.11 | 22.68 | 0.09182 | 26.93 | 25.27 | 207 |
| 아홉 | ALS | cells9ef_ALS_s0_cell6 | TRAINING_COMPLETE | 1 | 1.466 | 1.466 | 2148219 | 2148219 | 4.543 | 14.62 | 0.1023 | 25.36 | 20.93 | 217 |
| 아홉 | ALS | cells9ef_ALS_s0_cell7 | TRAINING_COMPLETE | 1 | 2.018 | 2.018 | 2634615 | 2634615 | 5.596 | 16.88 | 0.1025 | 25.43 | 24.41 | 233 |
| 아홉 | ALS | cells9ef_ALS_s0_cell8 | TRAINING_COMPLETE | 2 | 5.327 | 6.695 | 6515841 | 6515841 | 13.45 | 27.53 | 0.09381 | 29.06 | 25.36 | 217 |
| 넷 | ALS | 칸 4개 합 | 합 |  | 16.18 |  |  | 6423189 | 13.49 | 30.61 |  |  |  |  |
| 아홉 | ALS | 칸 6개 합 (칸 3·0·2 학습 안 함) | 합 |  | 17.2 |  |  | 6515841 | 13.45 | 27.53 |  |  |  |  |
