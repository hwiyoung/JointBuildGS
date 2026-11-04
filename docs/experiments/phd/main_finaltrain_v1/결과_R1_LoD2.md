# R1 LoD2 학습 기록

FINALTRAIN 덧붙임 적용. 메시·채점·그림: RESCORE 덧붙임 3에서 수행. scientific_verdict: null.


학습 시간과 GPU

| site | prior | attempt | status | gpu | start | finish | seconds | hours | model_directory | training_log |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1rep_b10 | LoD2 | 1 | TRAINING_COMPLETE_30000 | 1 | 2026-11-04T12:26:49.505132+09:00 | 2026-11-04T14:16:33.230081+09:00 | 6583.724731841125 | 1.8288124255114235 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_LoD2_s0/attempt1/model | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_LoD2_s0/attempt1/train.log |

저장 모델 경로

| site | prior | attempt | iteration | checkpoint | gaussian_ply | checkpoint_bytes | gaussian_ply_bytes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1rep_b10 | LoD2 | 1 | 7000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_LoD2_s0/attempt1/model/jbgs_complete/iteration_7000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_LoD2_s0/attempt1/model/point_cloud/iteration_7000/point_cloud.ply | 733489634 | 244501273 |
| R1rep_b10 | LoD2 | 1 | 15000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_LoD2_s0/attempt1/model/jbgs_complete/iteration_15000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_LoD2_s0/attempt1/model/point_cloud/iteration_15000/point_cloud.ply | 1735003938 | 601357214 |
| R1rep_b10 | LoD2 | 1 | 30000 | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_LoD2_s0/attempt1/model/jbgs_complete/iteration_30000/checkpoint.pth | /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_LoD2_s0/attempt1/model/point_cloud/iteration_30000/point_cloud.ply | 1735020706 | 601357214 |

7,000·15,000·30,000회 영역별 풀림

| site | prior | iteration | region | prior_descendants | released | fraction | r8_fraction | ratio_to_r8 | exceeds_twice_r8 | r8_source | r8_sha256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1rep_b10 | LoD2 | 7000 | 일치 | 50183 | 4469 | 0.0890540621325947 |  |  | False |  |  |
| R1rep_b10 | LoD2 | 7000 | 보존 | 106 | 48 | 0.4528301886792453 |  |  | False |  |  |
| R1rep_b10 | LoD2 | 7000 | 보정 | 62819 | 11024 | 0.17548830767761345 |  |  | False |  |  |
| R1rep_b10 | LoD2 | 7000 | 결측 | 162334 | 153622 | 0.9463328692695308 |  |  | False |  |  |
| R1rep_b10 | LoD2 | 15000 | 일치 | 82562 | 7809 | 0.09458346454785495 |  |  | False |  |  |
| R1rep_b10 | LoD2 | 15000 | 보존 | 122 | 53 | 0.4344262295081967 |  |  | False |  |  |
| R1rep_b10 | LoD2 | 15000 | 보정 | 96582 | 15817 | 0.1637675757387505 |  |  | False |  |  |
| R1rep_b10 | LoD2 | 15000 | 결측 | 405731 | 395116 | 0.9738373454333044 |  |  | False |  |  |
| R1rep_b10 | LoD2 | 30000 | 일치 | 82562 | 7901 | 0.09569777863908335 |  |  | False |  |  |
| R1rep_b10 | LoD2 | 30000 | 보존 | 122 | 53 | 0.4344262295081967 |  |  | False |  |  |
| R1rep_b10 | LoD2 | 30000 | 보정 | 96582 | 15883 | 0.164450932886045 |  |  | False |  |  |
| R1rep_b10 | LoD2 | 30000 | 결측 | 405731 | 395133 | 0.9738792451156062 |  |  | False |  |  |
