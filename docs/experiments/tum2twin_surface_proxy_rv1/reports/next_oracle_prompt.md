# Next prompt — T1 LiDAR oracle prior experiment design

아래 작업은 **새 실험 실행용 프롬프트**다. 이 문서를 작성한 post-analysis에서는 학습을 실행하지 않았다.

## 목적과 대상

`reports/nightly_rv1_20260728_2327/post_analysis/oracle_candidates.yaml`을 source of truth로 사용해 다음 후보를 building-centered local scene으로 비교한다.

- R0: `DEBY_LOD2_4908023` (30 frozen candidate views, cost tier low)
- R1: `DEBY_LOD2_4908050` (30 frozen candidate views, cost tier medium)
- R1: `DEBY_LOD2_4908176` (30 frozen candidate views, cost tier low)
- R2: `DEBY_LOD2_4906973` (30 frozen candidate views, cost tier low)
- R2: `DEBY_LOD2_4906985` (30 frozen candidate views, cost tier high)

`surface_proxy_R_v1`은 실험 대상 선택용 잠정 상대 strata이며 scientific pass/fail이 아니다. reference LoD2 roof geometry는 평가 때만 열고 training·view selection·densification에는 입력하지 않는다.

## 시작 gate

1. 현재 branch를 유지하고 rebase나 새 branch를 만들지 않는다.
2. 후보별 footprint, DIM/MVS class-6 current seed, ALS class-6 oracle seed, corrected camera binary, candidate image 30개, baseline result가 모두 존재하는지 확인한다.
3. `oracle_candidates.yaml`의 image name과 camera hash를 per-building/arm 전부 동일하게 고정한다. 하나라도 누락되면 그 building은 `blocked`로 기록하고 추측하지 않는다.
4. 먼저 local scene materialization과 B0 600-iteration cost smoke만 수행한다. 예상 GPU-hour는 현재 unknown이므로 smoke wall time·peak VRAM·final primitive count를 기록한 뒤 full queue를 산정한다.
5. P4의 coverage-aware densification 수식·threshold가 committed prereg/config에 없으면 P4는 실행하지 말고 `blocked_design_lock_missing`으로 기록한다. 임계값을 새로 발명하지 않는다.

## 모든 arm에서 고정할 조건

- Images/cameras: candidate YAML의 동일 per-building image list, corrected `images.bin` SHA-256 `28b38383a0b6d82656108e8f0e5e79711dcda93948ab2e89c1cd8f47215962a5`, 같은 train/eval policy.
- Appearance: `w_photo=1.0`, `photo_lam=0.2`, `downscale=1.0`, `sh_degree=3`, `sh_up_every=1000`.
- Budget: `max_iter=30000`; random seeds `1001`, `1002`; 같은 checkpoint/eval cadence.
- Optimizer/base densification: `fusion_w1_aprime_training_20260726.json` 값을 공통 사용 (`grow_grad2d=0.0002`, refine 500–15000/100 iter, reset 3000). P4의 coverage-aware 변경만 명시적 차이다.
- Shared regularizers: `w_nc=0.05`, `w_distort=100.0`와 schedule을 동일하게 고정한다. semantic/mutual/structure 및 기타 prior는 0으로 유지한다.
- LiDAR prior schedule for P2/P3/P4: depth 0.5→0.05, normal 0.05→0.005, signed normal, alpha-LSQ depth alignment, 기존 A-prime schedule을 그대로 사용한다.
- Mesh extraction: `fusion_w1_aprime_tsdf_20260726.json`의 TSDF/marching-cubes 설정과 최종 30k checkpoint를 동일 사용한다.
- Roofer: image digest `3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2`; `--id-attribute building_id --jobs 3 --srs EPSG:25832 --bld-class 6 --grnd-class 2 --lod22`; override 없음.
- 한 arm의 차이 외 init, loss, image/camera, iteration, seed, extraction, Roofer config가 동일한지 resolved-config diff로 증명한다.

## Arms

| Arm | Initialization | LiDAR depth/normal loss | Densification |
|---|---|---|---|
| B0 | current image-derived DIM/MVS class-6 seed | off | common base |
| P1 | ALS class-6 LiDAR seed only | off | common base |
| P2 | current image-derived DIM/MVS class-6 seed | on | common base |
| P3 | ALS class-6 LiDAR seed | on | common base |
| P4 | ALS class-6 LiDAR seed | on | P3 + preregistered coverage-aware rule only |

`seed only`은 photo loss가 꺼진다는 뜻이 아니다. 모든 arm의 appearance loss는 동일하며, P1은 LiDAR가 initialization에만 들어가고 LiDAR depth/normal loss가 0이라는 뜻이다.

## P4 design lock 요구

Coverage는 training-view LiDAR TIN valid mask와 rendered support 사이의 결손으로 정의해야 하며 evaluation-only reference를 사용하지 않는다. 정확한 eligibility, score, threshold, start/stop iteration, interaction with gradient-based growth를 config와 unit test로 먼저 고정한다. 기존 repository에서 이 계약을 찾지 못하면 P4 training을 시작하지 않는다.

## 계측과 산출

- Per arm/seed/building: wall time, peak VRAM, initial/final/pruned/grown primitive counts, loss/gradient share, seed survival, valid LiDAR support coverage.
- Same frozen surface-proxy protocol: precision/recall/F-score@0.1/0.2/0.5 및 양방향 p95. 가능하면 explicit mesh triangle distance를 별도 이름으로 추가하되 기존 proxy를 덮어쓰지 않는다.
- Same TSDF mesh와 Roofer readout: roof-plane F1, RMSZ, has_lod22, val3dity.
- 비교는 수치·관찰까지만 작성하고 scientific verdict는 사람이 내린다.
- 각 단계는 한 태스크 한 커밋, 실패 receipt append-only, 원본/기존 baseline 덮어쓰기 금지.
