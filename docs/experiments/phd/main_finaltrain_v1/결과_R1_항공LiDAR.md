# R1 항공LiDAR 학습 기록

FINALTRAIN 덧붙임 적용. 메시·채점·그림: RESCORE 덧붙임 3에서 수행. scientific_verdict: null.


학습 시간과 GPU

| site | prior | attempt | status | gpu | start | finish | seconds | hours | model_directory | training_log |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1rep_b10 | ALS | 1 | TRAINING_COMPLETE_30000 | 0 | 2026-11-04T12:26:49.505526+09:00 | 2026-11-04T13:49:27.079593+09:00 | 4957.573804166168 | 1.3771038344906021 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_ALS_s0/attempt1/model | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_ALS_s0/attempt1/train.log |

저장 모델 경로

| site | prior | attempt | iteration | checkpoint | gaussian_ply | checkpoint_bytes | gaussian_ply_bytes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1rep_b10 | ALS | 1 | 7000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_ALS_s0/attempt1/model/jbgs_complete/iteration_7000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_ALS_s0/attempt1/model/point_cloud/iteration_7000/point_cloud.ply | 707136034 | 235167193 |
| R1rep_b10 | ALS | 1 | 15000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_ALS_s0/attempt1/model/jbgs_complete/iteration_15000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_ALS_s0/attempt1/model/point_cloud/iteration_15000/point_cloud.ply | 2074645218 | 719089094 |
| R1rep_b10 | ALS | 1 | 30000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_ALS_s0/attempt1/model/jbgs_complete/iteration_30000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_ALS_s0/attempt1/model/point_cloud/iteration_30000/point_cloud.ply | 2074661090 | 719089094 |

7,000·15,000·30,000회 영역별 풀림

| site | prior | iteration | region | prior_descendants | released | fraction | r8_fraction | ratio_to_r8 | exceeds_twice_r8 | r8_source | r8_sha256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1rep_b10 | ALS | 7000 | 일치 | 63694 | 31958 | 0.5017427073193708 |  |  | False |  |  |
| R1rep_b10 | ALS | 7000 | 보존 | 3345 | 2391 | 0.7147982062780269 |  |  | False |  |  |
| R1rep_b10 | ALS | 7000 | 보정 | 790 | 492 | 0.6227848101265823 |  |  | False |  |  |
| R1rep_b10 | ALS | 7000 | 결측 | 530 | 251 | 0.47358490566037736 |  |  | False |  |  |
| R1rep_b10 | ALS | 15000 | 일치 | 125183 | 72990 | 0.5830663908038631 |  |  | False |  |  |
| R1rep_b10 | ALS | 15000 | 보존 | 4982 | 3935 | 0.7898434363709353 |  |  | False |  |  |
| R1rep_b10 | ALS | 15000 | 보정 | 1703 | 1308 | 0.7680563711098062 |  |  | False |  |  |
| R1rep_b10 | ALS | 15000 | 결측 | 839 | 450 | 0.5363528009535161 |  |  | False |  |  |
| R1rep_b10 | ALS | 30000 | 일치 | 125183 | 73069 | 0.583697466908446 |  |  | False |  |  |
| R1rep_b10 | ALS | 30000 | 보존 | 4982 | 3944 | 0.7916499397832196 |  |  | False |  |  |
| R1rep_b10 | ALS | 30000 | 보정 | 1703 | 1311 | 0.7698179682912507 |  |  | False |  |  |
| R1rep_b10 | ALS | 30000 | 결측 | 839 | 451 | 0.5375446960667462 |  |  | False |  |  |
