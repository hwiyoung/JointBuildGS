# B0 LoD2 학습 기록

FINALTRAIN 덧붙임 적용. 메시·채점·그림: RESCORE 덧붙임 3에서 수행. scientific_verdict: null.


학습 시간과 GPU

| site | prior | attempt | status | gpu | start | finish | seconds | hours | model_directory | training_log |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0_b10 | LoD2 | 1 | TRAINING_COMPLETE_30000 | 1 | 2026-11-04T09:54:38.224652+09:00 | 2026-11-04T11:45:37.094490+09:00 | 6658.869542879984 | 1.8496859841333289 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_LoD2_s0/attempt1/model | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_LoD2_s0/attempt1/train.log |

저장 모델 경로

| site | prior | attempt | iteration | checkpoint | gaussian_ply | checkpoint_bytes | gaussian_ply_bytes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B0_b10 | LoD2 | 1 | 7000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_LoD2_s0/attempt1/model/jbgs_complete/iteration_7000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_LoD2_s0/attempt1/model/point_cloud/iteration_7000/point_cloud.ply | 788955362 | 266213846 |
| B0_b10 | LoD2 | 1 | 15000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_LoD2_s0/attempt1/model/jbgs_complete/iteration_15000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_LoD2_s0/attempt1/model/point_cloud/iteration_15000/point_cloud.ply | 2372628834 | 822378854 |
| B0_b10 | LoD2 | 1 | 30000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_LoD2_s0/attempt1/model/jbgs_complete/iteration_30000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/B0_b10/ft_LoD2_s0/attempt1/model/point_cloud/iteration_30000/point_cloud.ply | 2372645922 | 822378854 |

7,000·15,000·30,000회 영역별 풀림

| site | prior | iteration | region | prior_descendants | released | fraction | r8_fraction | ratio_to_r8 | exceeds_twice_r8 | r8_source | r8_sha256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0_b10 | LoD2 | 7000 | 일치 | 86030 | 8464 | 0.0983842845519005 |  |  | False |  |  |
| B0_b10 | LoD2 | 7000 | 보존 | 66 | 24 | 0.36363636363636365 |  |  | False |  |  |
| B0_b10 | LoD2 | 7000 | 보정 | 11697 | 4609 | 0.394032657946482 |  |  | False |  |  |
| B0_b10 | LoD2 | 7000 | 결측 | 809277 | 790496 | 0.9767928657307695 |  |  | False |  |  |
| B0_b10 | LoD2 | 15000 | 일치 | 117298 | 24687 | 0.2104639465293526 |  |  | False |  |  |
| B0_b10 | LoD2 | 15000 | 보존 | 71 | 21 | 0.29577464788732394 |  |  | False |  |  |
| B0_b10 | LoD2 | 15000 | 보정 | 15841 | 6631 | 0.41859731077583484 |  |  | False |  |  |
| B0_b10 | LoD2 | 15000 | 결측 | 2826807 | 2805047 | 0.9923022689557511 |  |  | False |  |  |
| B0_b10 | LoD2 | 30000 | 일치 | 117298 | 24721 | 0.2107538065440161 |  |  | False |  |  |
| B0_b10 | LoD2 | 30000 | 보존 | 71 | 22 | 0.30985915492957744 |  |  | False |  |  |
| B0_b10 | LoD2 | 30000 | 보정 | 15841 | 6641 | 0.419228584054037 |  |  | False |  |  |
| B0_b10 | LoD2 | 30000 | 결측 | 2826807 | 2805079 | 0.9923135891484632 |  |  | False |  |  |
