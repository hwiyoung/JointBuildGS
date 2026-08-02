# C3 첫 실행 전략 DRAFT v2

- 상태: `DRAFT_NOT_EXECUTION_AUTHORITY`
- 대상 조건: `C3_GS_image` — 외부 3D prior 없이 현재 영상에서 얻은 공통 기반만 쓰는 GS
- `scientific_verdict: null`
- Semantic R2는 원본 R1 RGB가 아니라 exact-937 COLMAP-undistorted training RGB만 사용한다.
- 입력 manifest는 crosswalk의 membership만 기록하며 RGB를 미리 읽지 않는다. 각 RGB의 bytes/SHA-256은 실제 inference read 한 번에서 계산하고, inference 전에 COLMAP camera 및 대응 geometric depth와 width/height가 일치해야 한다.
- 기존 raw-R1 completion은 재사용하거나 resize하지 않는다. `EXACT_937_COLMAP_UNDISTORTED_R2` 전용 namespace의 add-once 완료 건만 resume한다.
- 이 문서는 producer 구현, Experiment Host handoff, 학습 실행을 승인하지 않는다.

## 한 문장 결정

정확히 같은 937개 영상·pose로 장면 전체를 한 번 학습하되, 초기점은 **전체 SfM sparse와 결과를 보지 않고 고른 AOI dense MVS voxel seed의 합집합**으로 고정한다. 평가 대상 72개 중 점수는 development 51개에서만 열고 validation 11개와 held-out 10개는 보지도 않는다.

## 이 선택의 연구 의미

C3의 질문은 “현재 영상만으로 재구성했을 때 어느 정도 가능한가”이다. 따라서 현재 영상에서 나온 SfM, dense MVS, depth, semantic은 C3–C5가 함께 쓰는 공통 영상 기반이며 외부 prior가 아니다. 반대로 UAS LiDAR, 기존 ALS, LoD1, LoD2 및 독립 평가 reference는 학습 입력이 될 수 없다.

과거 sparse-only pilot에서는 texture가 약한 건물의 초기 지원점이 거의 없었다. 그래서 sparse-only를 다시 반복하지 않는다. 동시에 43,942,554개 dense 점 전체를 직접 넣으면 24 GB GPU와 4백만 primitive 상한을 지킬 수 없으므로 이것도 금지한다. 이번 전략은 이 두 극단 사이에서, 결과를 보기 전에 계산 자원만으로 dense seed 크기를 정하는 계약이다.

## 1. 입력과 공간 범위

- 공통 기반 ID: `B_CURRENT_CANDIDATE_c205892c390997b5`
- 원 영상 962개 중 exact image–pose pair 937개를 장면 전체 학습에 사용한다. 제외 25개는 복구하거나 대체하지 않는다.
- 영상·pose 멤버십 hash: `dd9b446e11c978ef8223858f08571bfea832e0d33517b24c1e573060244f4e2c`
- image–camera pair hash: `7d1f90ecb79ee19acfbfedb0b7cf78083349c7669678a1f883c5034a41a89ccc`
- AOI: EPSG:25832, bbox `[690791.74, 5335864.05, 691154.65, 5336353.85]`
- AOI GeoJSON hash: `93728956ecfbbb24521b4fa4aec745fec176d4c6c94e10cef272934dcf9d9061`
- SfM sparse 371,808점은 전부 포함한다.
- dense source는 `dim_dense.ply` 43,942,554점이다. 원본 전체를 직접 학습 초기점으로 쓰지 않는다.
- gravity는 이미 영상 기반 terrain normal에서 계산한 `[0.0022003022295437485, -0.0038866451918428023, -0.9999900262798882]`를 그대로 재사용한다.

## 2. dense seed를 결과 없이 고르는 방법

producer가 구현될 때 raw dense source를 자연 처리 흐름에서 딱 한 번 읽는다. 같은 stream에서 다음을 함께 수행한다.

1. non-finite 점을 제외하고 frozen AOI로 자른다.
2. 0.10 m, 0.20 m, 0.40 m의 deterministic voxel map과 각 unique voxel 수를 동시에 만든다.
3. voxel index는 EPSG:25832의 고정 원점 `[0, 0, 0]`에서 각 축을 `floor((coordinate-origin)/voxel_m)`로 계산한다. 기존 `voxelcenternearestneighbor` 계보와 맞추기 위해 대표점은 voxel center에 가장 가까운 원 점으로 하며, 거리 동률은 world XYZ 사전순 뒤 source row로 고정한다. random subsampling은 없다.
4. 0.10 → 0.20 → 0.40 m 순서로 검사해, dense seed가 3,000,000점 이하이고 24 GB VRAM 사전검증을 통과하는 가장 세밀한 해상도를 고른다.
5. 선택된 해상도의 derivative 하나만 기록한다. 어느 후보도 통과하지 못하면 실패로 닫고 값을 임의 변경하지 않는다.

0.40 m는 과거 결과가 좋았다는 뜻의 최적값이 아니다. `≤3M / 24 GB`를 지키기 위한 가장 거친 engineering fallback lock이다. 이 preflight는 metric, 평가 reference, 렌더 결과, loss curve를 열기 전에 끝나야 한다.

초기 primitive는 `전체 SfM sparse + 선택된 dense seed`로 concat한다. sparse-only와 full 43.94M dense direct init은 모두 금지한다. 초기 seed는 5,000 iteration까지 pruning으로 제거하지 않으며, 전체 primitive hard cap은 4,000,000개다. cap에 닿으면 새 primitive 성장은 멈추되 pruning은 계속한다.

## 3. 영상만 쓰는 공통 semantic

C3–C5는 exact 937 RGB에서 동일한 GroundedSAM producer를 사용한다. 이 producer에는 footprint, building ID, pose 기반 건물 crop, UAS, ALS, LoD1, LoD2가 들어가지 않는다.

- 고정 prompt 순서: class 1 `roof`; class 2 `facade`, `wall`; class 3 `ground`, `road`, `pavement`
- GroundingDINO box threshold: 0.30
- text threshold: 0.25
- SAM multimask: false
- class 1: roof
- class 2: facade/wall
- class 3: ground/road/pavement
- class 0: unknown/ignore — loss에서 제외
- 같은 class mask는 union한다. class가 겹치면 GroundingDINO score가 큰 class를 택하고, 동점이면 낮은 class ID를 택한다.
- GroundingDINO `856dde20…`, Segment Anything `dca509fe…`, BERT snapshot `86b5e093…`와 두 checkpoint의 size/SHA-256은 `configs/c3_first_wave_v2/c3_image_semantic_producer_v1.json`에 고정했다. 실제 inference 전에 기존 receipt와 live cache가 일치해야 한다.

학습에서는 semantic을 켜고 `w_sem=0.1`, `sem_detach_geometry=false`, `lr_sem=0.0025`로 고정한다.

## 4. 고정 학습 recipe

- representation: gsplat planar 2D Gaussians
- 한 장면, 한 strategy, 한 job, seed 0
- exact 937 views, native scale, 30,000 iterations
- SH degree 3, 1,000 iteration마다 승급
- photo: `0.8 × L1 + 0.2 × (1-SSIM)`, `w_photo=1.0`
- image-derived geometric depth: finite·positive pixel만, scale 1.0, `w_depth=0.03`; 5,000 iteration warm-up 뒤 5,000 iteration 동안 선형 ramp
- external MVS normal-map supervision: OFF, unmounted, `load_normal=false`, `w_normal=0`
- intrinsic rendered-normal consistency: `w_nc=0.05`, iteration 7,000부터 일정
- distortion: `mean(rend_dist) / scene_scale²`, `w_distort=100`, iteration 3,000부터 일정; 대규모 장면에서는 expected/mean depth mode
- semantic: 앞 절의 image-only 3-class 계약, `w_sem=0.1`
- structure: `w_structure=1.0`, normal-alignment 0.08, coplanarity 0.01, grouping `g2`, voxel 2.0 m, normal cosine 0.92, distance tolerance 0.5 m, minimum group 30, warm-up 15,000, regroup 1,000
- densification: grow gradient 0.001, iteration 500–20,000, interval 200; opacity prune 0.005; opacity reset 3,000
- mutual, confidence, monocular, MVC와 별도 semantic-depth 항은 모두 0
- full-state checkpoints: 5k, 10k, 20k, 30k
- outcome을 보고 early-stop, retry, weight 변경, voxel 변경을 하지 않는다.

`g2_geometry`는 footprint partition을 필요로 하므로 금지하고 semantic argmax와 geometry를 함께 쓰는 `g2`만 쓴다. 외부 normal map을 끄는 것은 normal 정보를 전부 금지한다는 뜻이 아니다. 고정 gravity와 렌더 내부 normal-consistency는 서로 다른 역할로 유지된다.

## 5. 평가 경계

frozen roster는 72개이며 development 51, validation 11, held-out 10이다. 937-view whole-scene checkpoint 자체는 장면 전체를 표현할 수 있지만, 이 첫 실행에서 association과 score를 열 수 있는 것은 development 51개뿐이다.

- split source hash: `8dc33b86a126667b847ddf33f4ad4a56012f2bfc784c0742e573a421120f7309`
- development ID-set hash: `712cf0e7e635f049857302f4e5ffea825165d9fb38dd3091d0ab192d5974a68b`
- validation/held-out ID와 reference, 결과 namespace는 열지 않는다.
- Fusion W1, LoD1, LoD2, UAS, ALS, `R_ext`를 학습·선택·보정에 쓰지 않는다.
- UAS development reference는 C3 산출물이 outcome-free 상태로 seal된 뒤 점수 계산에만 사용할 수 있다. geometry 수정, crop, registration에는 사용할 수 없다.
- 이 결과는 development screening이며 confirmatory claim이나 자동 승자를 만들지 않는다.

## 6. 자원 상한과 중단 조건

- GPU: RTX 3090 class 1대, 24 GB VRAM
- dense seed: 최대 3,000,000점
- total primitives: 최대 4,000,000개
- training: 1 strategy × 1 seed × 1 job
- 최대 wall clock: 12시간
- 새 output 상한: 100 GB
- scientific retry: 0

입력 digest 불일치, 937-view membership 불일치, 금지 입력 mount/open, dense 후보 전부 preflight 실패, primitive cap 위반, non-finite state, 기존 namespace 충돌 중 하나라도 발생하면 실패로 닫는다. 실패 뒤 결과를 보고 설정을 바꿔 같은 첫 실행으로 재명명하지 않는다.

## 7. 아직 하지 않는 일

이 DRAFT는 결정 내용을 기계적으로 검증할 수 있게 만드는 문서다. 현재 one-read dense producer, image-only semantic producer, exact-view training guard와 primitive cap은 구현·unit-test까지 끝났고 실제 payload에는 아직 실행하지 않았다. 다음 실행 packet이 확인할 항목은 다음과 같다.

- exact geometric depth producer와 937-view binding 검증
- 실제 payload에서 dense preflight와 semantic inference 실행
- 금지 source가 mount되지 않는 실행 allowlist 검증

이 항목들이 구현·검증되고 사람이 별도 activation을 승인하기 전까지 Experiment Host handoff와 C3 실행 권한은 없다. `scientific_verdict`는 계속 `null`이다.
