# B0 항공LiDAR 학습 기록

FINALTRAIN 덧붙임 적용. 메시·채점·그림: RESCORE 덧붙임 3에서 수행. scientific_verdict: null.


학습 시간과 GPU

| site | prior | attempt | status | gpu | start | finish | seconds | hours | model_directory | training_log |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0_b10 | ALS | 1 | TRAINING_COMPLETE_30000 | 0 | 2026-11-04T09:54:38.225043+09:00 | 2026-11-04T11:09:16.078692+09:00 | 4477.853328091092 | 1.2438481466919702 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_ALS_s0/attempt1/model | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_ALS_s0/attempt1/train.log |

저장 모델 경로

| site | prior | attempt | iteration | checkpoint | gaussian_ply | checkpoint_bytes | gaussian_ply_bytes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B0_b10 | ALS | 1 | 7000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_ALS_s0/attempt1/model/jbgs_complete/iteration_7000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_ALS_s0/attempt1/model/point_cloud/iteration_7000/point_cloud.ply | 750490914 | 253386794 |
| B0_b10 | ALS | 1 | 15000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_ALS_s0/attempt1/model/jbgs_complete/iteration_15000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_ALS_s0/attempt1/model/point_cloud/iteration_15000/point_cloud.ply | 1734021282 | 601020290 |
| B0_b10 | ALS | 1 | 30000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_ALS_s0/attempt1/model/jbgs_complete/iteration_30000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_ALS_s0/attempt1/model/point_cloud/iteration_30000/point_cloud.ply | 1734037538 | 601020290 |

7,000·15,000·30,000회 영역별 풀림

| site | prior | iteration | region | prior_descendants | released | fraction | r8_fraction | ratio_to_r8 | exceeds_twice_r8 | r8_source | r8_sha256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0_b10 | ALS | 7000 | 일치 | 71569 | 37196 | 0.5197222261034805 |  |  | False |  |  |
| B0_b10 | ALS | 7000 | 보존 | 4694 | 2969 | 0.6325095867064338 |  |  | False |  |  |
| B0_b10 | ALS | 7000 | 보정 | 2701 | 2552 | 0.9448352462051092 |  |  | False |  |  |
| B0_b10 | ALS | 7000 | 결측 | 162 | 93 | 0.5740740740740741 |  |  | False |  |  |
| B0_b10 | ALS | 15000 | 일치 | 118898 | 76419 | 0.6427273797708961 |  |  | False |  |  |
| B0_b10 | ALS | 15000 | 보존 | 7740 | 5123 | 0.6618863049095607 |  |  | False |  |  |
| B0_b10 | ALS | 15000 | 보정 | 5116 | 4834 | 0.9448788115715403 |  |  | False |  |  |
| B0_b10 | ALS | 15000 | 결측 | 222 | 165 | 0.7432432432432432 |  |  | False |  |  |
| B0_b10 | ALS | 30000 | 일치 | 118898 | 76497 | 0.6433834042624771 |  |  | False |  |  |
| B0_b10 | ALS | 30000 | 보존 | 7740 | 5150 | 0.665374677002584 |  |  | False |  |  |
| B0_b10 | ALS | 30000 | 보정 | 5116 | 4834 | 0.9448788115715403 |  |  | False |  |  |
| B0_b10 | ALS | 30000 | 결측 | 222 | 165 | 0.7432432432432432 |  |  | False |  |  |
