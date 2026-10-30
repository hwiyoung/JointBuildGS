# 후보 고르기 시험 실행 상태

갱신: 2026-10-31T02:15:11.000269+09:00

학습 완료 **24/24판**. 실행 중 수치는 마지막 100회 기록 기준이다. 채점과 기준 충족은 results/status.json 및 기준 표에서 별도로 확인한다.

| 판 | 실행 상태 | 반복 |
|---|---|---:|
| cp_equal_sh3_B173_ALS | COMPLETE | 3000 |
| cp_wrong_sh3_B173_ALS | COMPLETE | 3000 |
| cp_right_sh3_B173_ALS | COMPLETE | 3000 |
| cp_wrong_sh0_B173_ALS | COMPLETE | 3000 |
| cp_equal_sh0_B173_ALS | COMPLETE | 3000 |
| cp_right_sh0_B173_ALS | COMPLETE | 3000 |
| cp_equal_sh3_R1_LoD2 | COMPLETE | 3000 |
| cp_wrong_sh3_R1_LoD2 | COMPLETE | 3000 |
| cp_right_sh3_R1_LoD2 | COMPLETE | 3000 |
| cp_wrong_sh0_R1_LoD2 | COMPLETE | 3000 |
| cp_equal_sh0_R1_LoD2 | COMPLETE | 3000 |
| cp_right_sh0_R1_LoD2 | COMPLETE | 3000 |
| cp_equal_sh3_B173_LoD2 | COMPLETE | 3000 |
| cp_wrong_sh3_B173_LoD2 | COMPLETE | 3000 |
| cp_right_sh3_B173_LoD2 | COMPLETE | 3000 |
| cp_wrong_sh0_B173_LoD2 | COMPLETE | 3000 |
| cp_equal_sh0_B173_LoD2 | COMPLETE | 3000 |
| cp_right_sh0_B173_LoD2 | COMPLETE | 3000 |
| cp_equal_sh3_R1_ALS | COMPLETE | 3000 |
| cp_wrong_sh3_R1_ALS | COMPLETE | 3000 |
| cp_right_sh3_R1_ALS | COMPLETE | 3000 |
| cp_wrong_sh0_R1_ALS | COMPLETE | 3000 |
| cp_equal_sh0_R1_ALS | COMPLETE | 3000 |
| cp_right_sh0_R1_ALS | COMPLETE | 3000 |

설정은 candpick_v1.json의 고정 해시를 사용한다. 학습 손실은 전체 사진의 L1+D-SSIM이며 후보의 불투명도·색만 갱신한다. 매 판 종료 시 바탕과 후보 기하의 학습 전후 메모리 해시를 대조한다.

scientific_verdict: null
