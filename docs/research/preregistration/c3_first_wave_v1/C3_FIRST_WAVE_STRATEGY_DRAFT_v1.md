# C3 첫 개발실험 전략 DRAFT v1

- status: `DRAFT_NOT_EXECUTION_AUTHORITY`
- independent review: `PASS_AS_STRATEGY_DRAFT / ACTIVATION_BLOCKED`
- condition: `C3_GS_image` (`no-external-prior GS`)
- decision context: `DEC-P1-010`–`DEC-P1-013`
- C3 execution: `PROHIBITED_UNTIL_SEPARATE_HUMAN_APPROVAL_AND_ACTIVATION`
- authorized run IDs: 없음
- validation / held-out building access: `PROHIBITED`
- C4 / C5 execution: `PROHIBITED`
- scientific_verdict: `null`

## 한 문장 결론

**C1/C2 개발 결과는 끝났고, 다음 한 번의 C3 개발실험은 동일한 937개 영상·pose와
그 영상에서 만든 MVS만 사용해 한 개의 GS 장면을 학습한 뒤, 개발 51동에서 C2의 연결
실패·관측 누락·높이 불일치가 줄어드는지를 확인하는 실험이다.** UAS LiDAR는 학습이
끝나고 C3 산출물이 봉인된 뒤 점수를 재는 데만 쓴다.

이 DRAFT는 무엇을 구현하고 실행할지를 명확히 정하지만 실행 승인은 아니다.
`DEC-P1-013`이 승인한 것은 C1/C2 development뿐이다. C3 실행은 이 문서의 독립 검토,
별도 사람 승인, 구현/config/test commit, 새 two-host handoff activation 뒤에만 가능하다.

## 왜 이 전략인가

R4의 C1/C2 결과는 다음 세 가지를 보여 줬다.

1. C2는 51동 중 50동을 생성했고, 한 동은 MVS component가 평가 건물과 연결되지 않아
   실패했다.
2. C2의 독립 UAS 수직 관측 coverage는 대부분 1.0이지만 일부 건물에서 크게 낮았다.
3. C1/C2의 roof-normal 오차가 paired 50동에서 동일했고, 많은 건물의 차이는 반복되는
   component 단위 높이 이동으로 설명됐다. 즉 첫 C3에서 우선 볼 것은 새로운 roof type
   추측이 아니라 **연결성, coverage, 장면 좌표계 안의 상대 높이 일관성**이다.

C1은 UAS 입력을 UAS 계열 reference로 다시 본 `SELF_REFERENCE_UPPER_BASELINE`이므로
C2나 C3와 독립 정확도 순위를 매기지 않는다. 위 관찰은 C3의 진단 초점을 정할 뿐 C1
geometry를 C3 target으로 전달하지 않는다.

## 199동, 72동, 51동과 C3의 관계

- 199동은 선택 AOI의 전체 연구 대상이다.
- 199동 중 raw UAS 관측이 최소 4 cell 있던 건물은 129동이다.
- 품질 필터와 모든 condition support를 통과한 pilot 평가 후보는 72동이다.
- 현재 결과를 볼 수 있는 것은 그중 development 51동뿐이다. validation 11동과 held-out
  10동의 reference와 결과는 계속 닫아 둔다.

C3는 51개의 별도 모델을 학습하지 않는다. 정확히 한 개의 937-view 장면 모델을
학습하고, 동결된 장면 surface에서 51동 결과만 평가한다. 장면 영상 자체에는 AOI 전체가
보이지만 validation/held-out building ID, bbox, UAS reference와 결과는 학습·read-out·
선택에 사용하지 않는다. 이는 같은 장면을 재구성하면서 method 선택용 결과만 공간
split으로 분리하는 현재 연구계약이다.

Full-scene checkpoint와 stable-ID-blind component 생성은 허용하지만, development
association 전에는 어느 component도 validation/held-out 건물로 식별하지 않는다.
development 51동과 연결되지 않은 component는 정성 열람, promotion, adapter 비교에
사용하지 않고 validation/held-out result namespace도 만들지 않는다.

199→72의 이유, threshold와 통과/불통 실제 사례는
`docs/research/preregistration/gate_s0/uas_eligibility_explainer_v1/`에 별도 정리돼 있다.

## C3에 들어가는 것과 들어가지 않는 것

### 들어가는 exact common base

공통 source ID는 `B_CURRENT_CANDIDATE_c205892c390997b5`이고 membership은
962 images / 937 calibrated image-pose pairs / 25 exclusions다.
937 pair-set digest는
`7d1f90ecb79ee19acfbfedb0b7cf78083349c7669678a1f883c5034a41a89ccc`다.
source manifest, camera-ID set, exclusion set은 각각
`c205892c390997b57b13ee211bbc264c45800770bb84f0b2698c45d3c656fd74`,
`43b70a448dc3d4bad6a06b5352eee0f1ba2cd6e5bc0d57bf7e53f4c11cd79ca7`,
`a55a811ffe580790c199b65dc57d518890b04d6110ff7c7a2e4cfeb30e6fcb02`다.
Development 51 ID-set은
`712cf0e7e635f049857302f4e5ffea825165d9fb38dd3091d0ab192d5974a68b`다.

| Component | first-wave 상태 | C3 역할 |
|---|---|---|
| camera / pose | `ON / READY` | 학습 view와 투영 좌표계 |
| SfM sparse 371,808 points | `ON / READY` | 전부 초기 primitive에 포함 |
| exact common dense MVS | `ON / READY` | AOI 0.40 m deterministic voxel seed로 한 번 변환해 초기화 |
| terrain-MVS gravity | `ON / READY` | 기존 추정값 재사용; run별 재추정 금지 |
| per-view depth | `OFF / READY_OFF` | loss와 생성 모두 0 |
| normal-map supervision | `OFF / READY_OFF` | loss와 생성 모두 0 |
| confidence | `OFF / READY_OFF` | weighting과 생성 모두 0 |
| segmentation | `OFF / READY_OFF` | loss와 생성 모두 0 |

frozen gravity는
`[0.0022003022295437485, -0.0038866451918428023, -0.9999900262798882]`다.
기존 checkpoint/attestation을 재사용하며 UAS로 다시 정렬하거나 gravity를 다시 계산하지
않는다. Dense seed는 canonical AOI만 outcome-blind하게 crop하고 0.40 m voxel마다
lexicographic first point 하나를 선택한다. 3,000,000점을 넘으면 무작위 절삭하지 않고
preflight를 실패시킨다. 이 derivative는 C3–C5 공통 초기화 후보로 한 번만 만들고
operation ID와 hash를 재사용한다.

### 절대로 들어가지 않는 것

- Current UAS LiDAR / evaluation reference
- Existing ALS
- LoD1, LoD2/LoD3 geometry, RoofSurface, roof type, semantic label, final model
- C1/C2 output geometry 또는 이를 만든 Roofer output
- external roofprint와 `R_ext`
- 1,104-image vendor MVS, unbound `scene.mvs`, `dim_v1.laz`
- validation/held-out reference payload와 outcome

UAS는 C3 native/extracted/Stage-3 산출물이 add-once로 봉인된 뒤 development score-only
단계에서 처음 연다. loss, initialization, registration, reconstruction component
association, crop,
early stopping, checkpoint 선택 또는 `R_derived` 생성에 사용하지 않는다.
`OFF / READY_OFF` 네 component와 위 금지 자산은 weight만 0으로 두는 것이 아니라
학습·추출 container에 mount하지 않고 open attempt 자체를 실패로 처리한다.

단계별 container는 전체 artifact root를 받지 않는다. Dense derivative 단계는
`dim_dense.ply`와 frozen AOI/config만, training 단계는 exact 937 images와
`cameras.bin/images.bin/points3D.bin` 및 완성된 dense derivative만, scoring 단계는
봉인된 C3 출력과 development UAS reference만 read-only allowlist로 받는다. `stereo/`,
`scene.mvs`, `rigs.bin`, `frames.bin`, `dim_v1.laz`, ALS, LoD1/LoD2, validation/held-out
root는 container에서 보이지 않아야 한다.

여기서 금지하는 `component association`은 reconstruction component의 생성·병합·선택에
UAS를 쓰는 것이다. 모든 geometry와 Roofer input/output이 이미 봉인된 뒤에는 R4와 같은
`FROZEN_DEVELOPMENT_EXACT_SCORE_CELL_TO_CONDITION_COMPONENT_ASSOCIATION_V1`을
`SCORE_IDENTITY_ONLY`로 한 번 적용한다. 이 사후 연결은 geometry modification, crop,
registration을 모두 금지하며 zero-overlap은 G0 기술 실패로 남긴다.

## 한 번의 C3 학습 recipe

첫 실험은 여러 loss를 동시에 탐색하지 않는다. 먼저 해석 가능한 no-external-prior
control 하나를 만든다.

| 항목 | DRAFT 고정값 |
|---|---|
| representation | `gsplat` planar 2D Gaussian primitives |
| scene / seed | exact 937-view scene / seed `0` |
| initialization | all SfM sparse + deterministic 0.40 m dense-MVS AOI seed, `concat` |
| dense seed protection | iteration 5,000까지 prune 보호, 이후 동일 규칙으로 release |
| image scale / SH | native scale 1.0 / SH degree 3, every 1,000 |
| photometric loss | `1.0 × (0.8 L1 + 0.2 (1-SSIM))` |
| self normal consistency | `0.05` |
| distortion | `0.0`; 현 TUM metric scale에서 미정규화 항의 collapse 위험을 피함 |
| external/per-view priors | depth, normal-map, mono, semantic, mutual, structure, MVC 모두 `0.0` |
| learning rates | means `1.6e-4`, scales `5e-3`, quats `1e-3`, opacity `5e-2`, SH0 `2.5e-3`, SHN `1.25e-4` |
| densification | start 500, stop 25,000, every 100; opacity reset every 3,000 |
| pruning/growth | opacity `0.005`, grad2d `5e-4`, scale3d grow `0.01`, prune `0.1` |
| updates | exactly 30,000; quality early stopping 없음 |
| checkpoints | full-state 5k / 10k / 20k / 30k + final export 1개; primary는 항상 30k |

이 recipe는 C2의 높이 오차값을 직접 loss로 넣지 않는다. 영상 photometric evidence가
MVS 초기 geometry를 재최적화하게 하고, normal consistency는 지붕 방향을 guardrail로
유지한다. C2에서 보인 component별 Z 차이는 C3의 native→extracted→Roofer 각 단계에서
추적해 어느 단계가 고쳤거나 악화했는지 구분한다.

실제 engine key는 추상 이름에 맡기지 않고 구현 config에 전부 쓴다:

```yaml
seed: 0
max_iter: 30000
load_depth: false
load_normal: false
load_semantic: false
normal_dir: null
mono_normal_dir: null
mono_depth_dir: null
w_photo: 1.0
photo_lam: 0.2
w_depth: 0.0
w_normal: 0.0
w_nc: 0.05
w_distort: 0.0
w_mono_depth: 0.0
w_sem: 0.0
w_mvc: 0.0
w_mutual: 0.0
w_structure: 0.0
init_pointcloud_mode: concat
seed_protect: true
seed_protect_until_iter: 5000
full_state_checkpoint: true
full_state_checkpoint_steps: [5000, 10000, 20000, 30000]
full_state_resume: off
```

`w_nc`가 self normal consistency이고 `w_normal`은 금지된 per-view normal-map loss다.
단일 seed는 first development screening에만 허용하며 결과에
`SEED_VARIANCE_NOT_ESTIMATED`를 붙인다. Python/NumPy/PyTorch/CUDA seed와 알려진
비결정 연산은 acceptance receipt에 기록한다.

### 이 숫자의 출처와 한계

0.40 m dense voxel은 현재 추적 중인 TUM dense-seed conversion config
`configs/input_and_alignment/tum_mob/seed_prep_dense.json`(Git blob
`fea920195cd74804196f3cb2dc61400a1dbd8a25`)에서, 30k·learning rate·densification
control은 `configs/input_and_alignment/tum_vanilla_proper.yaml`(Git blob
`5d951717e570523facb1108a30325792a2c1fc0b`)에서, 5k seed release를 구현할 engine은
`src/stage2/train.py`(Git blob `1e1cd1fa081af12170c61bdb64f9bdbd324f34db`)에서 가져온
**비보호 capability starting point**다. Fusion W1/held-out 결과를 선택 근거로 쓰지
않았다. `w_distortion=0`은 first control에서 미정규화 추가항을 넣지 않는 보수적
정의이며 C1/C2 결과로 최적 weight라고 주장하지 않는다.

이 숫자는 아직 새 C3 config가 아니다. implementation task가 exact source/code/config,
project image, CUDA/PyTorch/gsplat version과 함께 다시 결속하고 zero-payload smoke를
통과시켜야 activation-ready가 된다.

### 원인 위치를 찾는 필수 audit

frozen dense-MVS seed/component lineage는 densify/prune 뒤에도 추적한다. init, 5k, 10k,
20k, 30k, 각 adapter, Roofer 단계마다 다음 machine-readable 표를 add-once로 만든다.

- component ID와 parent/merge/split lineage
- initial seed 수, surviving seed 수와 survival fraction
- initial occupied voxel 대비 support recall
- frozen up 방향 signed/absolute component-balanced `delta_Z`
- XY centroid drift
- merge / split / unassociated component 수
- finite/NaN, primitive 수, bytes와 stage operation ID

이 audit는 UAS를 열기 전에 완성되며 candidate 선택용 정답 지표가 아니다. 결과 해석은
다음처럼 precommit한다.

- native 30k에서 Z drift/support loss 발생 → 다음 별도 DRAFT에서 MVS-drift anchor ×
  support-retention 2×2 검토 가능
- native는 안정적이고 adapter끼리만 갈림 → surface-extraction 문제
- adapter도 안정적이고 Roofer에서만 실패 → Stage-3 component/read-out 문제
- 위 evidence 전에는 C3 regularizer arm을 추가하지 않음

## 한 모델에서 비교할 두 surface adapter

학습을 두 번 하지 않고 동일한 30k checkpoint에서 아래 두 surface만 만든다.

1. `A_DIRECT_DEPTH_FUSION`: exact 937 pose의 rendered depth를 직접 point로 융합한다.
2. `A_TSDF_MC`: 같은 rendered depth와 view set을 TSDF에 적분한 뒤 Marching Cubes
   surface를 sampling한다.

두 adapter는 동일한 exact 937-view list/hash, frame/up, rendered-depth add-once cache를
공유한다. depth near/far/invalid rule/unit, fusion/TSDF voxel·truncation·weighting,
Marching Cubes iso/sampling density, normal rule을 구현 commit에서 exact config/hash로
고정한다. TSDF origin/voxelization은 frozen frame에서 Z recentering이 0인지 audit한다.
이 값들은 장면 scale과 VRAM preflight를 통과해야 하므로 현재 DRAFT에서 임의 숫자를
발명하지 않는다. **이 빈칸은 C3 학습 recipe의 재튜닝이 아니라 Stage-3 adapter
implementation freeze 항목**이며, 실행 activation 전 반드시 채워져야 한다.

각 extracted surface는 C1/C2에서 쓴 outcome-free geometry rule과 같은 1 m grid,
terrain lower-envelope, 지면 대비 2.5 m 이상의 building 분리, 8-neighbor component,
최소 4 point 규칙을 사용한다. 각 condition component의 class-6 XY convex hull에서
`R_DERIVED_NON_GT_CONVEX_HULL_V1`을 만들고 external roofprint 없이 동일한 pinned
Roofer 1.0.0 경로로 LoD2.2를 read-out한다. validation/held-out bbox는 열지 않는다.

최종 P2 adapter는 아직 고르지 않는다. 두 candidate를 같은 표로 비교하고 사람이 볼
provisional nomination만 만든다. G0/G1이 악화되지 않고 pooled와 group-balanced
coverage/surface-RMSE 방향이 일치할 때만 한 candidate를 지명한다. 방향이 충돌하거나
차이를 지지하지 않으면 `NO_SELECTION`으로 남긴다. 47/1/1/1/1 구조에서 네 singleton이
group-balanced 평균의 80%를 차지하므로 자동 lexicographic winner를 만들지 않는다.

Normal은 activation 전 synthetic known-tilt fixture가 perturbation 방향과 크기에 따라
score 변화를 검출하면 report guardrail로 쓴다. sensitivity test가 실패하면 normal은
`REPORT_ONLY_EVALUATOR_NOT_DISCRIMINATIVE` null-reason을 붙인다. 통과 여부와 무관하게
첫 wave adapter nomination에는 normal을 쓰지 않고 normal-map supervision도 켜지 않는다.
G3, G4와 `PASS_usable` threshold가
없으므로 nomination이 곧 validation 실행 권한은 아니며 별도 사람 결정이 필요하다.

## 평가와 사람이 보게 될 결과

개발 51동·5그룹(`47/1/1/1/1`)에 대해 다음을 모두 보고한다.

- G0/G1 생성·schema 성공과 failure reason
- vertically scored coverage
- height MAE, RMSZ, RMSXY
- surface RMSE / p95
- roof-normal median / p95 angle
- building-level 전체 표, group별 표, unweighted group-balanced 표
- C2→C3 paired 변화: G0 generated↔not-generated, G1 technical transition, coverage와
  continuous residual의 양방향 변화
- native GS, extracted surface, exact Roofer input, LoD2 output의 단계별 failure 위치

경량 case sheet는 51동 전부 만들고, mechanism sheet는 R4에서 outcome 전에 고른 5개
group 대표를 그대로 재사용한다. top orthographic, common oblique, principal section,
geometry-only, normal-color, height-color camera/renderer를 UAS score 전에 hash-bind한다.
결과가 나쁜 건물만 사후 선택해 대표 그림으로 바꾸지 않는다.

G3, G4, `PASS_usable`, p-value, confidence interval, confirmatory·population·TUM2TWIN
전체 일반화 주장은 금지한다. vertical datum 미확정 상태에서 absolute geodetic Z
정확도라고 부르지 않고, 현 frozen association에서의 provisional surface residual로
보고한다. scientific_verdict는 계속 `null`이다.

## 비용과 중단 계약

| 항목 | hard cap |
|---|---:|
| strategy variants | 1 |
| training seeds / jobs | 1 / 1 |
| extraction adapters | 2, 동일 checkpoint 재사용 |
| GPU | RTX-3090-class 1개, VRAM 24 GB 이하 |
| training wall-clock | 12시간 이하 |
| aggregate GPU time | 12 GPU-hours 이하 |
| 새 output | task 전체 100 GB 이하 |
| checkpoints retained | full-state 4 + final export 1 = 최대 5 |
| automatic scientific retry | 0 |

Rendered depth는 exact 937 views를 한 번만 만들고 두 adapter가 같은 cache를 재사용한다.
Adapter 실행은 최대 2회, lightweight case sheet는 51장, mechanism panel은 최대 30장이다.
Training/checkpoint 50 GB, rendered-depth cache 20 GB, adapter별 10 GB, Stage-3/report
10 GB의 sub-cap을 둔다. 합계가 100 GB를 넘으면 preflight에서 optimizer를 시작하지
않는다. Roofer는 2 CPU, 8 GB RAM, attempt당 600초, quality retry 0을 유지한다.

다만 **outcome-blind component 수에 따른 Roofer unique-operation 최대값과 전체 pipeline
wall-clock은 implementation preflight 전까지 아직 수치 미동결**이다. 이 두 값과 adapter
수치가 채워지기 전에는 strategy DRAFT는 검토할 수 있어도 execution activation은
요청할 수 없다.

cap을 넘기거나 OOM/timeout/partial output이 생기면 범위·seed·iteration을 자동 확대하지
않고 technical blocker로 닫는다. 복구가 필요하면 같은 partial namespace를 덮어쓰지
않고 checkpoint identity를 확인한 별도 recovery task를 만든다.

다음은 optimizer update 전에 fail-closed한다.

- exact common-base identity 또는 962/937/25 membership 불일치
- dense derivative가 3,000,000점을 초과하거나 frame/transform이 불명확함
- validation/held-out/UAS/ALS/LoD1/LoD2/1,104-image MVS의 금지 mount·read
- 미승인 depth/normal/confidence/segmentation 생성 또는 nonzero loss
- external roofprint 사용
- 결과를 본 뒤 seed/schedule/loss/cost cap 변경
- 기존/partial output namespace 충돌
- dirty tree, `HEAD != origin/main`, receipt chain 불일치
- non-null `scientific_verdict`
- project image/GPU/driver/code/config digest drift, NaN/Inf 또는 zero primitive
- full-state RNG/optimizer/dataloader cursor mismatch
- 30k가 아닌 checkpoint를 adapter가 소비하거나 두 adapter 중 하나가 reference open
  전에 미완성

## 중복 계산 방지와 ownership

- Images.zip, OPF.zip, R1 15.7 GB, 기존 C1/C2 input은 다시 전수 해시하지 않는다.
- exact B_current, gravity, split과 R4 result는 기존 attestation/hash record를 검증해
  재사용한다.
- dense-MVS seed derivative는 operation identity당 한 번 만들고 C3 training과 향후
  C4/C5 common base가 재사용한다.
- 두 adapter는 동일한 한 개의 C3 checkpoint를 읽고 학습을 반복하지 않는다.
- Roofer input이 같은 operation identity면 재사용하고 condition/building별 중복 실행을
  금지한다.

현재 R4 `300-closed` 뒤 writer는 Work Host에 있다. C3 실행은 새 task, output namespace,
DRAFT packet과 activation이 필요하다. activation 시 Work Host가 000을 push한 뒤 writer를
내려놓고, Experiment Host가 100-accepted부터 Return/200/300까지 sole writer가 된다.

Activation packet은 아래 네 consumer의 path/bytes와 기존 checkpoint record/hash를
정확히 결속해야 한다. raw를 별도 hash-only pass로 다시 읽지 않는다.

- `data/work/mvs/colmap_dense/sparse/cameras.bin` — 64 bytes
- `data/work/mvs/colmap_dense/sparse/images.bin` — 114,415,526 bytes
- `data/work/mvs/colmap_dense/sparse/points3D.bin` — 33,476,840 bytes
- `data/work/mvs/openmvs/dim_dense.ply` — 659,138,498 bytes
- common checkpoint `030-dense_mvs_and_gravity.json` — 2,951 bytes,
  SHA-256 `b301d3dc7dec2423ff5760c47db4dfef4f62e919b5aac5808a30c82a9330a8f8`

Exact 937 image files는 `data/work/mvs/colmap_dense/images`에서 기존
`gate_s0_image_member_inventory_v1.csv`(Git blob
`d05ee144d5728247189e843e30ad86ae161832ba`, canonical SHA-256
`de9acff049fca4fa14582620a69617157f99b4b5c333938c01b648740ece2b4a`)와
`gate_s0_image_camera_ledger_v1.csv`(Git blob
`2869ede94b6447dfb3f043cb346f14c0e4e29ca7`, canonical SHA-256
`8c1e89040869e800c34ebd8a06c2b5185524330fc5d56e594b41686173c465b0`)에 결속한다.
최초 자연 read에서 같은 byte buffer로 manifest SHA를 확인하고 decode하며 별도 hash-only
pass는 금지한다.

Canonical AOI는 EPSG:25832 bbox
`[690791.74, 5335864.05, 691154.65, 5336353.85]`, GeoJSON SHA-256
`93728956ecfbbb24521b4fa4aec745fec176d4c6c94e10cef272934dcf9d9061`로 묶는다.
과거 selection에 LoD2 GroundSurface overlay가 관여했다는 provenance는 숨기지 않되,
RoofSurface/roof type/performance는 사용되지 않았고 C3에서는 per-building footprint를
crop으로 열지 않는다.

실행 전에는 zero-scientific-payload checkpoint writer smoke, synthetic 두-adapter smoke,
Roofer writable-workdir smoke, deterministic dense-seed 3M preflight, prohibited-root mount
검사, 30k checkpoint seal→score-only phase boundary receipt, partial namespace collision
fail-closed test를 모두 통과해야 한다.

Dense derivative config는 activation 전에 bbox boundary, source/local/canonical frame,
0.40 m voxel origin과 `floor((xyz-origin)/0.4)` 규칙, representative/source-row tie-break,
non-finite/RGB/duplicate 처리, output schema/path/count/bytes/digest와 operation ID를 모두
machine-readable하게 채운다. 동일한 완전 manifest만 `REUSED_EXACT`, partial은 terminal,
동일 ID 충돌은 fail-closed다. 실제 point count와 peak-VRAM preflight가 24 GB를 넘으면
voxel이나 점 수를 자동 바꾸지 않는다.

제안 task/handoff/namespace는 `P2-C3-FIRST-WAVE-v1`,
`P2-W2C-C3-FIRST-WAVE-v1`,
`artifact://JointBuildGS/phase-payloads/p2-baselines/c3_first_wave_v1/P2-C3-FIRST-WAVE-v1/`다.
이 namespace가 비어 있지 않으면 시작하지 않는다. Handoff receipt가 아닌 external
add-once control record `control/150-pre-reference-sealed_v1.json`이
30k checkpoint, native audit, 두 surface, 두 Roofer input/output, adapter config,
renderer/view list와 모든 completion/digest를 묶은 뒤에만 UAS scoring container를 연다.
Canonical handoff receipt chain은 000→100→200→300이며 이 control record가 chain을
변경하지 않는다.
새 output digest는 serialization/save stream에서 함께 계산하며 봉인 후 전수 재해시하지
않는다.

두 adapter는 별도 reconstruction condition이 아니다. Development result key는
`(building_id, method_id=C3_GS_image, adapter_id)`이며 사람의 별도 선택 전에는 어느
adapter도 final C3로 승격하지 않는다. Mixed sparse+dense init의 최초 component ID와
densify/split/merge/prune 뒤 ID inheritance는 stable building ID/UAS 없이 outcome-free
source component에서 시작하도록 implementation config/hash에 고정한다.

## 이 DRAFT 뒤의 한 단계

독립 검토에서 이 전략이 통과하면 사람이 확인할 결정은 하나다.

> **위 한 개의 C3 recipe와 두 adapter를 C3 implementation target으로 승인하고, 남은
> activation blocker를 해소할 구현/config/test 및 handoff DRAFT 준비를 승인할 것인가?**

이 결정 자체는 C3 실행 권한이 아니다. 승인되면 다음 Work task는 adapter 수치·
source/config/test를 채운 구현 commit과 Experiment Host handoff DRAFT를 만드는 것이다.
Roofer unique-operation cap, 전체 wall-clock, toolchain/config/test가 결속·독립 검토된
뒤 별도의 사람 실행 승인과 activation이 필요하다. 승인 전에는 C3를 실행하지 않는다.
