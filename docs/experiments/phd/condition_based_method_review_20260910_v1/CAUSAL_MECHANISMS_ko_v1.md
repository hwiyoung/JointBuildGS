# 2단계 — 보존·배제·보정이 실패하는 경로의 문헌 기반 원인 분석

- 작성일: 2026-09-10
- task_id: PHD-CAUSAL-LITERATURE-20260910
- 상태: `CAUSAL_LITERATURE_ANALYSIS / CONDITIONAL_METHOD_DESIGN / NO_NEW_EXPERIMENT`
- scientific_verdict: null

## 1. 결과 수준의 부족에서 원인 수준의 질문으로

“유효한 것은 보존하고 부정확한 것은 약화·배제한다”는 복원 요구다. 방법 설계에는 **그 정보의 유효성을 왜 잘못 추정하는지, 유효하게 추정해도 왜 필요한 교정이 일어나지 않는지, 감독을 잘 맞추는데도 왜 최종 구조가 틀릴 수 있는지**를 추가로 설명해야 한다. 잘못된 정보의 배제와 현재 표면의 복원도 서로 다른 달성 항목이다.

진행 순서는 **① 기존 방법의 성공·부족 → ② 목표에 중요한 잔여와 경쟁 원인 → ③ 원인을 겨냥한 방법·검증**으로 유지한다. [앞선 네 조건 비교](STEP1_FOUR_CASE_COMPARISON_ko_v1.md)를 원인 분석으로 확장한다. 먼저 작성된 [방법 구상](METHOD_AND_MINIMUM_TESTS_ko_v1.md)은 채택안이 아니다. 이번 분석에 맞춰 방법 가설을 좁히거나 버릴 수 있다.

상위 조건은 기존 기하/원영상의 **OO, OX, XO, XX** 네 가지다. 아래 원인들은 새 입력 분류가 아니라 각 조건 안에서 검사할 처리 경로다. 원영상 O인데 파생 depth/normal이 틀릴 수 있고, 같은 영역의 위치·방향·세부마다 조건이 다를 수 있다. 판정 미확인은 확인 상태이며 다섯 번째 조건이 아니다.

기존 헌장·DEC-P1-025·실험 계보는 보존한다. 이번 탐색에서 ALS, GS, LoD2, 동결 confidence, 명시적 소스 선택·원인 분류기를 필수로 정하지 않는다.

## 2. 원인을 어디까지 확인했는가

| 원인 질문 | 선행에서 확보한 근거 | 증거 상태 | 우리 목표와 연결 |
|---|---|---|---|
| 신뢰도가 정확성 대신 현재 모델과의 일치를 측정하는가? | DebSDF의 잔차 기반 uncertainty 목적과 저자의 예외 설명 | **수식·구현 확인 / 예외의 일반적 빈도 미확인** | OO-3의 정확한 세부 감독을 버리거나 XO-3의 공통 오답을 계속 믿을 수 있음 |
| 가중치가 틀린가, 가중치로 만들 수 있는 답 자체가 제한되는가? | SenFuNet의 convex TSDF 혼합과 단일센서 전용 outlier gate | **완성법 잔여 보고 + 구현의 행동 범위 확인** | XO에서 원영상 단서가 남아도 두 기하 후보의 혼합만으로 수정이 불가능할 수 있음 |
| 정확한 감독이 주변의 유효 구조까지 줄이는가? | DebSDF의 SDF→density 편향 분석과 변환 교체 ablation | **기전 설명 + 기존 해법으로 개선된 ablation** | 입력 정확성만 검사해도 구조 손상의 전달 경로가 남을 수 있음 |
| 외관 오차를 기하·생성으로 줄이거나 기하 오류를 외관으로 감추는가? | CoMe의 appearance/densification/variance 비교; GaussianUpdate의 appearance mask 제거 비교 | **기존 해법으로 개선된 ablation / 일부 조건 악화도 존재** | OO/OX 손상, XO 수정 누락이 모두 가능. RGB 품질과 기하 품질을 분리해야 함 |
| 틀린 prior를 약화해도 수정할 변수·표면이 잠겨 있는가? | GeoGS의 prior loss와 별도 보호; EnerGS의 중심 갱신 경로 분리 | **구현·가정 확인 / 해당 원인에 의한 우리 장면 실패는 미입증** | XO-1 수정과 인접 OO/OX 보존의 핵심 경쟁 가설 |
| 감독이 정확해도 loss가 필요한 영상 간 관계를 제약하지 않는가? | SPARF의 정확한 depth를 쓰는 진단과 다중시점 대응 loss | **저자 통제 비교 / 완성법이 해결한 범위** | 잘못된 정합을 불량 기하나 confidence 문제로 오인할 위험 |
| 정보가 없거나 평가가 다른 표면을 보고 있는가? | ND-SDF의 관측 부족 한계; 기존 P1/P2의 가림·광선 규약·참조 피복 감사 | **저자 한계 / 기존 개발 관측** | XX의 식별 한계와 OO/XO의 처리 실패를 구분 |

이 표는 모든 선행의 공통 실패를 주장하지 않는다. 외부 기존 기하가 없는 논문은 관련 원리의 구성요소·원인 근거이며 우리 네 조건을 직접 검증한 경쟁 실험이 아니다.

## 3. 원인 A — 모델과의 일치를 감독의 정확성으로 읽는 문제

### 확인된 기전

DebSDF는 현재 렌더 깊이·법선과 단안 감독 사이의 잔차를 이용해 uncertainty를 학습한다. 저자는 잘못된 감독도 다른 감독과 일치하면 낮은 uncertainty, 올바른 감독도 불일치하면 높은 uncertainty가 될 수 있다고 설명한다. [원문 §III-B](https://arxiv.org/html/2308.15536v3#S3.SS2).

이를 설명하는 **우리의 제한된 수학적 분석**은 단일 depth 항 `log U + |r|/U`다. 다른 결합·정규화·clip을 제외하고 U만 최적화하면 `U*=|r|`이다. 이것이 학습하는 것은 현재 잔차의 크기이며 GT 기하 오차와 같다는 보장은 없다. 현재 기하가 공통 오답에 맞춰진 경우에는 오답의 잔차가 작고, 아직 복원하지 못한 진짜 세부를 지지하는 감독은 잔차가 클 수 있다. 실제 알고리즘 전체를 이 단일 항으로 환원하지 않는다.

[공식 loss.py L238–327](https://github.com/davidxu-jj/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/model/loss.py#L238)는 uncertainty 학습과 직접 depth/normal 감독의 detach·mask를 구분한다. **높은 uncertainty가 모든 기하 gradient를 완전히 끊는다고 표현하면 과도하다.** uncertainty 생성에 쓰는 feature·normal·volume weights 등 다른 계산 경로의 존재와 실제 영향은 별도로 확인해야 한다.

### 무엇이 아직 미확인인가

이것만으로 “confidence 학습은 실패한다”거나 “학습 데이터 편향이 원인이다”라고 판정할 수 없다. 다중시점·다중감독의 일치가 실제 정확성과 잘 대응하면 해당 방식은 유효하다. 현재 필요한 검사는 **어떤 지역에서 일치와 정확성이 갈라지는가**다.

SenFuNet의 매끄럽지만 덜 정확한 표면 선호도 신뢰 순위 오판의 실제 예다. 하지만 그것이 학습 분포, 입력 특징, GT 가공, 최적화 중 무엇 때문인지는 분리되지 않았다. “데이터가 매끄러운 표면에 편향되어서”는 현재 설명 후보다. 논문은 기존 특징·outlier 감독으로 개선한 성공도 제시한다. [SenFuNet Appendix J/Fig.17 및 Tables7·9·15](https://arxiv.org/html/2204.03353v2#A10).

**우리 설계에 주는 조건:** 신뢰도 추가보다 먼저 기존 confidence·다중시점 검사가 이 오류를 이미 구별하는지 본다. 부족이 남을 때 감독의 체계적 편향과 장면 기하의 오차를 구분하는 추정 규칙을 검토한다. 기존 ND-SDF식 감독 보정으로 충분하면 그 도입이 우선이다.

## 4. 원인 B — 추정기가 좋아져도 허용된 융합으로 답을 만들 수 없는 문제

SenFuNet은 두 센서가 모두 관측한 voxel에서 `v = α v₁ + (1−α) v₂`, `0≤α≤1`로 TSDF를 결합한다. 공식 test 경로의 outlier gate는 한 센서만 관측한 영역에 적용된다. 이 범위 제한은 양쪽 outlier가 남는다는 저자 설명과 맞는다. [filtering_net.py L193–223](https://github.com/eriksandstroem/SenFuNet/blob/43c1682e29c700df4577d9dcf0ac3b8ebdd8f496/modules/filtering_net.py#L193), [test_fusion.py L190–227](https://github.com/eriksandstroem/SenFuNet/blob/43c1682e29c700df4577d9dcf0ac3b8ebdd8f496/test_fusion.py#L190).

**우리의 수학적 분석:** 출력 가능한 값은 `[min(v₁,v₂), max(v₁,v₂)]`다. 평가 참값이 그 밖이면 어떤 α도 잔여를 없애지 못한다. `v₁=v₂`이면 `∂v/∂α=0`이다. 또한 두 관측의 계수 합이 항상 1이면 둘 다 기각하는 상태를 나타내지 못한다. 반대로 두 오차가 참값을 양쪽에서 감싸면 혼합이 유익할 수 있다. Fig.17의 각 voxel이 어느 경우인지는 측정하지 않았다.

따라서 세 현상을 구분해야 한다.

- 가능한 출력 중 잘못된 것을 고름: **신뢰 추정·목적함수·최적화의 경쟁 원인**.
- 가능한 어떤 출력도 충분히 정확하지 않음: **입력 후보·출력 표현의 제한**.
- voxel 오차는 작지만 추출된 경계가 나쁨: **목적함수·표면 추출의 불일치 후보**.

학습은 overlap voxel의 TSDF L1을 포함한다. 그러나 **L1이 평균화를 강제한다는 설명은 틀리다.** 정확한 endpoint가 있으면 L1도 그것을 선호할 수 있다. 경계 실패를 loss 원인으로 확정하려면 α 추정과 추출을 분리해야 한다. [loss.py L28–45](https://github.com/eriksandstroem/SenFuNet/blob/43c1682e29c700df4577d9dcf0ac3b8ebdd8f496/utils/loss.py#L28).

Stereo RGB 특징도 사용하므로 “원영상을 보지 않는 방법”이라고 하지 않는다. 다만 공개 예제는 `w_rgb=True`, `stereo_warp_right=False`이며 depth 위치에 특징을 누적한다. 원영상의 대응 정보가 파생 표현에서도 보존되는지는 별도다. 예제 설정과 논문 실제 run 설정의 동일성은 미확인이다. [replica.yaml](https://github.com/eriksandstroem/SenFuNet/blob/43c1682e29c700df4577d9dcf0ac3b8ebdd8f496/configs/fusion/replica.yaml#L7), [fuse_pipeline.py L328–410](https://github.com/eriksandstroem/SenFuNet/blob/43c1682e29c700df4577d9dcf0ac3b8ebdd8f496/modules/fuse_pipeline.py#L328).

**우리 설계에 주는 조건:** XO-3에서 prior와 파생 감독이 함께 틀렸다면 상대 가중만 조정해 충분한지부터 검사한다. 부족하면 기존 감독 재추정·편향 보정·절대 유효성 검사·출력 자유도 확장을 대조한다. 둘 다 배제해 구멍을 만든 결과와 관측에 맞는 표면을 복원한 결과를 구분한다. 평가 GT를 이용한 최적 혼합 오차 하한은 **voxel별 TSDF 오차의 진단 하한**이며 방법 출력·학습값으로 쓰지 않는다. 이 하한이 작아도 공유망·공간 결합·정규화 때문에 동시 달성이 어려울 수 있고 최종 mesh 오차도 보장하지 않는다.

## 5. 원인 C — 정확한 감독도 표현·렌더링을 거치며 구조를 손상시키는 문제

### DebSDF: 입력 오류와 다른 전달 편향

DebSDF §III-E1/Fig.5는 얇은 물체를 비껴 배경을 보는 광선에도 SDF→density 변환 때문에 물체 근처에 가짜 렌더링 기여가 생길 수 있다고 분석한다. 올바른 배경 감독은 이 기여를 줄이지만, 공간적으로 연결된 SDF와 정규화 때문에 실제 얇은 구조까지 축소될 수 있다. **유효 감독을 잘 고르는 것만으로 해결되지 않는 전달 경로**다.

Table IV는 filtering·sampling·smooth 제어를 포함한 상태에 변환 보정을 추가해 ScanNet F-score 77.30→78.54를 보고한다. Table VIII는 geometric prior 없는 DTU에서도 변환 교체의 효과를 비교한다. 이것은 **기존 해법이 개선한 ablation**이며 완성 DebSDF의 미해결 실패로 재사용하지 않는다. [원문 §§III-E, IV-D/Figs.5·9·12](https://arxiv.org/html/2308.15536v3).

[공식 network.py](https://github.com/davidxu-jj/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/model/network.py#L354)에서는 변환과 렌더링이 연결된다. 관련 옵션은 ray sampling 경로도 바꾸므로 논문 모듈 ablation을 “실현된 모든 ray·weight가 동일한 비교”라고 부르지 않는다. SDF의 이 기전을 GS에 그대로 전이하지 않고, GS의 합성 깊이와 개별 표면 사이에도 별도 불일치가 있는지 조사한다.

### GeoGS 실제 깊이량: 표면 이동과 합성 기여 변화의 구별

공식 renderer는 expected/median depth를 `depth_ratio`로 섞는다. 기존 P1/P2 감사에서 확인한 실제 설정은 expected depth다. 출판 논문의 median 표현, 공식 코드의 선택지, 실제 run을 구분한다. [renderer L140–161](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/gaussian_renderer/__init__.py#L140).

**우리의 수학적 분석:** `D̂ = Σwᵢdᵢ / Σwᵢ`는 여러 표면의 합성값이다. 고정된 깊이들에서도 기여도 `wᵢ`가 바뀌면 D̂가 바뀐다. 설명을 위해 w를 독립변수로 보면 `∂D̂/∂wᵢ=(dᵢ−D̂)/Σwᵢ`이다. 실제 w는 opacity·가림·위치 등에 결합되어 있으므로 이것은 국소 진단식이다. 깊이 loss 감소가 개별 표면의 정확한 위치 이동을 보장하지 않으며, 보호된 중심이 유지돼도 합성 표면은 달라질 수 있다.

**우리 설계에 주는 조건:** confidence나 prior 가중의 성패를 최종 mesh 하나로 판정하지 않는다. 감독 target→렌더 깊이→표면 기여→추출 표면을 연결해야 어느 변환·제약을 수정할지 정할 수 있다. 기존 surface/variance 제약이나 추출법이 충분하면 새 confidence 모듈을 만들 이유가 약해진다.

## 6. 원인 D — 외관·기하·생성이 서로 다른 문제를 대신 설명하는 경우

CoMe는 조명·시선 의존 오차가 기하 gradient와 과도한 생성을 유발하는 경로를 다루며, 합성색·법선만 맞추면 개별 primitive의 오류가 숨을 수 있다고 설명한다. Appearance, confidence, 생성 문턱, primitive variance를 구분해 개선한다. Table5에서 생성 문턱 보정을 제거하면 F1 .521→.516, Gaussian 수 1.27M→1.53M이다. **confidence를 바꾸면 생성 과정도 달라질 수 있음**을 보여주는 분리 비교다. [원문 §§3.2–3.4, Table5](https://arxiv.org/html/2603.24725v2).

[train.py L203–290](https://github.com/r4dl/CoMe/blob/caf62f6402dd82a301f7aa9d43350209f7309911/train.py#L203)는 confidence로 RGB 항을 조절하고 다른 기하 항을 별도로 합친다. [gaussian_model.py L779–826](https://github.com/r4dl/CoMe/blob/caf62f6402dd82a301f7aa9d43350209f7309911/scene/gaussian_model.py#L779)는 낮은 confidence에서 clone/split 문턱을 높인다. [CUDA backward L1626–1689](https://github.com/r4dl/CoMe/blob/caf62f6402dd82a301f7aa9d43350209f7309911/submodules/diff-gaussian-rasterization/cuda_rasterizer/stopthepop/hierarchical_render.cuh#L1626)는 confidence 출력과 variance 항의 gradient 경로를 구분한다. Confidence를 키우기 위해 opacity를 직접 바꾸는 경로와 가중된 RGB를 통해 기하가 바뀌는 경로를 혼동하지 않는다.

성공은 보편적이지 않다. CoMe Appendix D.4/Table7의 동일 TSDF DTU 평균 Chamfer는 confidence까지 .64, variance 추가/full .65다. 해당 추가 제약의 악화 원인은 분리되지 않았다. 외부 prior 보존·수정은 원방법의 직접 검증 범위가 아니다.

보조 근거로 GaussianUpdate §4.3/Fig.3/Table3은 appearance 학습에서 layout-invariant mask를 제거하면 사라진 물체의 차이가 외관에 흡수되어 제거가 실패할 수 있다고 보고한다. Sparse point 추가 없이 densification만 사용한 비교도 새 물체 학습이 부족하다. 둘 다 **완성법이 개선한 ablation**이다. 기존 색 있는 GS·시간별 replay가 입력이므로 무색 이종 prior에 바로 적용한 성능 주장은 하지 않는다. [원문](https://arxiv.org/html/2508.08867v1#S4.SS3). 공식 학습 구현은 이번 확인 범위에서 확보하지 못했으므로 이 보조 주장은 논문 근거 수준이다.

**우리 설계에 주는 조건:** OX에서 RGB 오차를 낮추려다 맞는 구조를 바꾼다면 기존 appearance 모델·loss 전달 분리를 먼저 대조한다. XO에서 형상 오류를 색·opacity가 대신 설명한다면 기존 변수 분리·생성/삭제를 대조한다. 두 현상을 같은 “영상 loss가 약하다/강하다”로 설명하지 않는다.

## 7. 원인 E — prior 손실의 세기와 실제 수정 가능한 범위가 다름

GeoGS refinement에는 prior 깊이 loss가 남고, 근접한 building Gaussian의 기하 gradient 감쇠와 생성·삭제 보호가 별도로 작동한다. [train.py L805–831, L1140–1170](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L805), [gaussian_model.py L396–461](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/scene/gaussian_model.py#L396). 보호를 할당하는 prior 근접성은 현재 타당성 판정과 다르다. 이로 인한 XO 수정 제한은 **구현에서 도출한 가설**이며 모든 틀린 prior가 고정된다는 뜻은 아니다. Gradient .01배를 Adam의 실제 이동 .01배로 해석하지 않는다.

출판 논문 Table6은 depth/protection의 효용을 구분하고 Table7은 prior perturbation에서 building-scale 기하가 비교적 안정적임을 보고한다. 따라서 보호는 이미 성과가 있는 제어다. 원문 §§3.4, 5.4–5.5와 보존된 첨부 전문을 재확인했다. [출판사](https://www.sciencedirect.com/science/article/pii/S0924271626003588), [전문 계보](NEARBY_METHODS_ko_v1.md#7-출처와-검토-범위).

EnerGS는 한층 명시적으로 photo→기존 중심의 optimizer gradient를 차단하고 geometry energy로 중심을 갱신한다. 그러나 사진 유래 gradient 통계·view coverage가 force gate에 feedback하고 생성·opacity·covariance 경로도 남는다. **사진이 중심 변화에 전혀 영향을 주지 않는 단방향 방법이라고 하면 틀리다.** [train_energs.py L584–611, L704–708](https://github.com/ucla-mobility/EnerGS/blob/a222ed59b05a56eecf7b7199e02eb80bcb288775/train_energs.py#L704), [geometric relax L214–255 및 gate L346–397](https://github.com/ucla-mobility/EnerGS/blob/a222ed59b05a56eecf7b7199e02eb80bcb288775/energs/gaussian_model.py#L214).

Trusted occupied/free field의 타당성이 원문 가정이다. 그 field가 틀렸을 때 현재 영상으로 교정하는 것은 별도 미평가 질문이다. Table2/§5.4에는 제약·decoupling의 지표 간 trade-off가 있으며, prior occupancy 일치를 독립 현재 표면 정확도로 읽지 않는다. [EnerGS 원문](https://arxiv.org/html/2604.26238v1).

**우리 설계에 주는 조건:** prior depth weight와 구조 보호를 독립 요인으로 비교한다. 또한 중심 보호와 최종 표면 보존을 구분한다. 기존 제어의 적절한 설정으로 XO 수정과 OO/OX 보존이 함께 충족되면 추가 제어 원리의 필요성은 약해진다.

## 8. 원인 F — 데이터가 정확해도 loss가 필요한 관계를 묶지 않음

SPARF §5.2/Fig.3/Table3은 sparse/noisy-pose 조건에서 저자의 진단용 GT depth 감독만으로는 각 영상의 국소 형상을 맞추면서 전역 pose·geometry가 분리된 해에 머무를 수 있음을 보인다. 세계 좌표의 3D 관계를 감독하는 비교는 이를 개선한다. 실제 방법은 다중시점 correspondence loss를 이용한다. **정확한 감독의 존재와 그 감독이 올바른 관계에 전달되는 것은 다르다.** 이 GT 사용은 선행의 원인 진단이며 우리 연구의 GT 학습 허용을 뜻하지 않는다. [SPARF 원문 §5.2](https://arxiv.org/html/2211.11738#S5.SS2).

[공식 corres_loss.py L158–219](https://github.com/google-research/sparf/blob/91e633b708c9468cd64aa45934acdc9e781471c1/source/training/core/corres_loss.py#L158)는 현재 pose·렌더 depth로 양방향 reprojection residual을 만든다. 단순히 per-image depth 항을 더 세게 하는 것과 제약하는 관계가 다르다. 완성 SPARF의 이 성공을 미해결 gap으로 재사용하지 않으며, 외부 prior frame까지 자동으로 정합한다는 주장도 하지 않는다.

**우리 설계에 주는 조건:** 같은 표면·좌표·광선·가시성의 대응을 먼저 확인한다. 여러 면에서 비슷한 방향의 이동이 나타나면 국소 불량 prior보다 pose/registration을 경쟁 원인으로 둔다. 기존 정합·재투영 제어로 충분하면 새 국소 보호법의 기여를 축소한다.

### 보정 변수가 유효 제약까지 약화시키는 경우

ND-SDF의 [공식 system.py L195–221](https://github.com/zju3dv/ND-SDF/blob/f58f29466a5f43e80dedb0cd155f57dae7569347/models/system.py#L195)는 표면 법선 n을 학습 회전 Q로 보정한다. **우리 해석:** Q가 자유로우면 서로 다른 n에도 `Qn≈n_prior`인 Q를 만들 수 있어 보정 후 작은 잔차만으로 형상을 구별하기 어렵다.

원문 Table6/Fig.5의 보정만 사용한 Model A에서는 무텍스처 벽에 주름이 생겼고, 원래/보정 감독을 함께 쓰는 adaptive prior 추가로 F-score .632→.679를 얻었다. 추가 제어에는 normal과 depth가 함께 포함되므로 normal 항 단독 효과는 아니다. 완성법의 낮은 피복/local optimum 한계와 이 **해결된 ablation**을 구분한다. [원문 §4.2 및 §5](https://arxiv.org/html/2408.12598v3).

[loss.py L315–344](https://github.com/zju3dv/ND-SDF/blob/f58f29466a5f43e80dedb0cd155f57dae7569347/models/loss.py#L315)의 가중 계산은 `no_grad`지만 학습된 Q→다음 각도→다음 감독의 feedback은 남는다. 같은 각도로 depth까지 조절하는 [L187–190](https://github.com/zju3dv/ND-SDF/blob/f58f29466a5f43e80dedb0cd155f57dae7569347/models/loss.py#L187)의 단안 공통 편향 가정을 독립 metric prior에 자동 전용하지 않는다. “감독 보정을 더 자유롭게 하면 항상 유익하다”는 전제도 두지 않는다.

## 9. 우리 개발 관찰에 연결할 때의 현재 결론

기존 [P1/P2 원인 감사](../geogs_causal_followup_v1/CAUSAL_REVIEW_ko_v1.md), [DA3 입력 감사](../geogs_causal_followup_v1/DA3_INPUT_AUDIT_ko_v1.md), [P2 재평가](../p2_geometry_reassessment_v1/REASSESSMENT_ko_v1.md)를 읽었다. 새 데이터 질의·처리는 하지 않았다.

| 기존 관찰 | 현재 지지되는 설명 | 아직 구별되지 않은 원인 |
|---|---|---|
| P1/P2 native .005→.0005에서 일부 현재 방향의 형상 수정 | 동일 입력·같은 기록된 DA3 가중(.05)·같은 보호 수에서도 prior 깊이 제어가 결과에 영향을 줌 | 국소 gradient, opacity, 보호 membership별 실제 이동이 없어 prior loss가 잔여의 유일 원인이라고 못 함 |
| P2의 낮은 prior 가중 결과가 정성적으로 정돈되고 일부 정확도 개선, 전체 F1 하락 | 개선된 예측 표면과 피복 손실이 함께 존재. 외관만 좋아졌다고 하지 않음 | 감소한 F1만으로 세부 손상 위치·원인·평가 피복을 분리할 수 없음 |
| P2 골은 DA3와 최종 expected depth 모두 얕은 방향; anchor에도 복수 면 존재 | TSDF 이후에만 오류가 처음 생긴다는 설명은 약해짐 | 원 파생 감독, 가시성, half-pixel 규약, 기여도 혼합, anchor 생성·추출의 경쟁 원인이 남음 |
| P1의 일부 참조 투영점은 실제 사진에서 앞쪽 지붕에 가림 | 같은 픽셀에 뒤의 참조 깊이를 대조하면 감독 오차를 과장할 수 있음 | 다른 시선의 실제 유효 관측량을 이번 선택 표본만으로 일반화 못 함 |

P1/P2/P3 장면 번호를 OO/OX/XO/XX에 바로 대응시키지 않는다. P3 저가중 악화는 미검증 가설이다. GeoGS 논문의 binary valid mask, 선택적 공식 DA3 confidence, 실제 native의 비활성 상태를 구별한다. “전문 미확보·실제 결과 없음”이라는 과거 설명을 재사용하지 않는다.

## 10. 목표에 중요한 잔여와 현재 조사 우선순위

우선순위는 **목표 손실의 크기 × 허용 정보로 개선할 가능성 × 경쟁 원인을 구별할 가능성**에 근거한 조사 순서다. 발생 빈도를 측정한 중요도 순위가 아니다.

| 우선 | 목표에서 중요한 잔여 | 우선 구별할 원인 | 기존 해법의 충분성을 먼저 볼 대상 |
|---|---|---|---|
| 1 | **XO의 필요한 교정이 남으면서 같은 영역 OO/OX가 손상됨** | 감독이 잘못된 방향인가 / prior 제약인가 / 수정 경로·표현인가 | 기존 confidence·robust loss, prior weight와 보호의 독립 조정, 기존 변수 분리 |
| 2 | **입력에 존재하는 관측 가능 세부가 파생 감독·학습·추출에서 사라짐** | 정보 추출 편향 / 잔차 기반 거절 / 합성·정규화 / 생성 지원 부족 | 기존 감독 보정, DebSDF/CoMe 계열 전달·surface 제약, 기존 보완·추출 |
| 3 | **외관은 개선되지만 현재 기하가 충분히 교정되지 않음** | appearance·opacity의 대체 설명 / 정합 / 실제 관측 부족 | 기존 appearance 분리와 다중시점 관계 제약 |
| 경계 | **XX에서 관측되지 않은 현재 형상을 확정함** | 정보 부족과 과도한 자유도의 결합 | 불확실성·갱신 제한. 새 관측 없는 완전복원을 성공 요건으로 두지 않음 |

이 중 방법 기여에 가장 직접적인 질문은 **주어진 유효 정보를 기존 추정·제약으로 이용할 수 있는가, 이용할 수 없다면 어느 연산을 바꿔야 하는가**다. 원인이 입력 재처리나 기존 제어만으로 해결되면 그 사실도 연구 결과다.

## 11. 원인 질문별 최소 비교 — 계획만, 실행 없음

모든 비교를 한 번에 조합하지 않는다. 기존 산출물 진단으로 경쟁 원인을 좁힌 뒤 해당 행만 수행하는 설계다. 동일 입력 bytes·초기 구조·사용 감독·정합·평가/추출·계산 예산을 기본으로 고정하고, **검사하려는 요인만 의도적으로 변경**한다. 입력 후보 교체는 별도 앞단 진단으로 명시하며 동일 감독의 방법 우열 비교에 섞지 않는다.

| 질문 | 최소 비교·관찰 | 가설을 지지하는 결과 | 기각·축소 조건 |
|---|---|---|---|
| Q0. 같은 표면을 비교하는가? | 기존 입력·저장 깊이의 ray 규약, 가시성, frame, 참조 피복 대응. 향후 필요한 추가 산출은 별도 실행계획 | 불일치가 원인 후보별로 남음 | 대응·추출 규약을 맞추자 잔여가 사라지면 학습 제어 원인 주장 축소 |
| Q1. confidence의 일치가 정확성과 갈라지는가? | 같은 학습 상태에서 confidence·감독 잔차·평가 오차·관측 지지 대응. 이후 기존 confidence/robust 제어 vs 기존 감독 보정을 같은 backend에서 비교 | 낮은 confidence의 정확한 세부 또는 높은 confidence의 공통 오답이 반복되고 특정 기존 제어가 구별함 | 기존 confidence의 적절한 보정만으로 보존·수정이 회복되면 새 추정 원리 필요성 축소 |
| Q1b. 보정 변수가 기하 오류까지 설명하는가? | 원감독 / 보정만 / 보정+원감독 제약. 보정 전 표면 오차와 보정 후 감독 잔차를 함께 평가 | 보정 후 잔차는 줄지만 표면 오차가 커지고 기존 제약으로 회복됨 | 기존 adaptive prior로 충분하면 새 감독 보정 규칙의 필요성 축소 |
| Q2. 신뢰 추정인가, 허용 출력의 한계인가? | 같은 입력 TSDF의 평가 전용 voxel별 attainable-error 하한과 실제 TSDF 오차를 대조. 최종 GT 기반 선택값을 방법에 공급하지 않음 | 하한도 크면 후보·표현 제한. 하한은 작고 실제만 나쁘면 추정·최적화·목적함수/공간 결합을 조사하며 confidence 오판을 단독 확정하지 않음. Mesh 추출은 별도 대조 | 기존 후보 교체/절대 validity 검사로 충분하면 새 융합 원리 주장 축소 |
| Q3. prior loss인가, 보호인가? | 같은 anchor에서 prior depth weight 2수준 × 보호 2수준의 최소 2×2. DA3 제어의 실현 궤적·생성/삭제 경로 기록 | 보호 해제에서만 XO 교정 또는 weight 완화에서만 교정 등 구별되는 상호작용 | 적절한 기존 조합이 같은 영역의 보존·교정을 모두 달성하면 신규 제어의 필요성 축소 |
| Q4. loss 전달·합성인가, 입력인가? | 입력·confidence를 고정하고 해당 표현의 기존 전달/variance 제약만 비교. 감독·합성 depth·표면 기여·최종 mesh를 함께 관찰 | 입력을 바꾸지 않고 구조·세부가 회복됨 | 기존 제약/추출로 충분하면 새 마스크·신뢰도는 기여 후보에서 제외 |
| Q5. 외관 보정인가, 필요한 기하 수정인가? | 기존 appearance 보정 유무를 먼저 비교. confidence 효과가 쟁점일 때만 광도 가중 × 생성 문턱 2×2 추가 | RGB/생성량과 기하 교정·손상의 변화가 분리됨 | 계산량 또는 기존 appearance 모델로 설명되면 새 구조 제어 효과 주장 축소 |
| Q6. 정합·영상 간 관계가 병목인가? | 같은 허용 영상/pose 초기값에서 기존 재투영·정합 제어를 대조. 정합 이후 frame 일치 유지 | 공통 방향 잔여와 구조 오류가 함께 줄어듦 | 정합으로 충분하면 source validity 원인 주장 축소 |

독립 변인 하나를 바꿔도 적응형 sampling·opacity·제어 궤적까지 같아지는 것은 아니다. 이를 “완벽히 동일한 실행”이라고 하지 않는다. 순수한 변수 효과가 필요하면 그 차이를 기록·통제하는 후속 최소 비교만 추가한다.

**평가:** 같은 물리 영역 안에서 초기 유효 요소의 손상과 초기 불량 요소의 잔여·교정량을 함께 보고한다. 초기 위치에서 사라진 불량 면, 현재 위치에 실제 생긴 면, 새로 손상된 유효 면을 분리한다. 정확도·완전성·현재성·관측 가능 세부·외관·시간/메모리를 각각 기록한다. 평균 F1로 모두 합치지 않으며 기존 방법의 성공·제안법의 악화도 포함한다. 평가 참조가 없는 세부는 그 부재만으로 false positive라 단정하지 않는다.

GT는 평가 전용이다. 사후 O/X 분류와 오차 하한은 평가 산출이고 학습·mask·confidence 보정·정합·파라미터 선택에 전달하지 않는다. 특히 SPARF의 GT 감독 진단이나 SenFuNet의 GT TSDF 학습을 우리 대상 장면에 도입하지 않는다. 원방법 전체 비교와 공통 backend에 요소를 도입한 비교는 별개로 보고한다.

## 12. 방법·학위 기여의 조건부 판단

| 평가 축 | 현재 판단 |
|---|---|
| 문제 설정의 차별성 | 불균일한 이종 기존 기하와 현재 영상에서 보존·교정·세부·외관을 함께 요구하는 범위는 연구 가치가 있다. 요구의 병렬 나열만으로 신규성은 확정되지 않음 |
| 원인 설명 | 문헌에서 잔차-정확성 불일치, 융합 행동 제한, 감독 전달 편향, 변수 경로, 정합 원인을 구별했다. 우리 조건에서 어떤 원인이 실제 지배적인지는 검증 대상 |
| 기존 요소 도입 | confidence/robust loss, 감독 보정, appearance 분리, surface 제약, 가중/보호 분리, 다중시점 관계 제약을 우선 후보로 둠. 도입·단순 조합만으로 새 방법이라 하지 않음 |
| 새 추정 원리 후보 | 기존 검사·보정이 실패하는 조건에서 **감독의 공통 편향과 실제 기하 오류를 구별하는 추가 제약**. 독립 관측이 구별하는 내용을 특정해야 하며, 단순 confidence 재명명은 제외 |
| 새 수정 제약 후보 | 올바른 감독도 합성·변수 결합으로 유효 표면을 손상시키는 경우 **최종 표면에 미치는 교정과 손상을 연결해 허용 갱신을 정하는 규칙**. 기존 variance/보호로 충분하지 않은 이유가 필요 |
| 검증 기여 | 같은 영역의 교정-손상과 처리 단계별 원인을 구별하는 비교는 검증 가치가 있다. 평가 항목 분리 자체는 방법 신규성이 아님 |

현재는 위 두 원리 후보 중 무엇을 채택할지 동결하지 않는다. 원인 분석과 구체 규칙 설계는 병행할 수 있으며 완전한 인과 입증까지 기다릴 필요는 없다. 다만 각 후보는 어느 기존 해법 이후의 잔여를 겨냥하는지와 실패 조건을 명시해야 한다. 하나의 보정 규칙으로도 이 연결이 충분하면 방법 기여 후보가 될 수 있다.

## 13. 감사 범위·정정·예외

- 원문과 공식 구현은 위 commit으로 고정해 정적으로 읽었다. 선행 수치는 저자 결과이며 재현 성능이 아니다. 새 학습·추론·렌더·재구성·방법 실험·프로젝트 도구/테스트 실행 없음.
- 기존 파일·코드·payload·서비스·진행 중 작업은 수정하지 않았다. 이 파일만 추가했다. 과거 자료를 소급 교정하지 않고 해석 보완을 여기에 남긴다.
- **기존 카드 해석 보완:** DebSDF의 직접 감독 차단을 전체 기하 gradient 차단으로 넓히지 않는다. EnerGS의 직접 photo→중심 차단을 모든 영상 feedback 부재로 넓히지 않는다. SenFuNet의 RGB 특징 사용을 명시한다. GeoGS의 논문 median과 실제 expected depth를 분리한다.
- SenFuNet `utils/loss.py` L74–150에는 논문 outlier label 설명과 다른 오차·부호 조건, tensor에 대한 `is True/False` 등 정적 감사가 필요한 구문이 있다. 실행 및 논문 checkpoint 계보를 확인하지 않았으므로 Fig.17 실패 원인으로 사용하지 않았다. 별도 구현 검증 필요사항으로만 남긴다.
- SPARF의 CVF HTML 접근 오류는 arXiv 원문 및 공식 코드로 대체했다. GaussianUpdate의 추정 GitHub API 경로는 404였고 공식 project·저자 publication 페이지에는 학습 코드 링크를 확인하지 못했다. 구현이 없다고 단정하지 않고 논문 근거 수준으로 제한했다.
- 독립 감사의 범위는 SenFuNet 융합·기각, DebSDF/ND-SDF 감독·전달, CoMe/EnerGS 변수 경로다. 통합 문서도 독립 읽기 검토했다. 검토에서 지적된 voxel별 오차 하한과 confidence 추정·공간 결합·최종 mesh 오차의 구별을 §4/Q2에 반영했다.

`scientific_verdict: null`
