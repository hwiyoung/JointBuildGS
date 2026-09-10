# 유효 정보 보존·부정확한 영향 배제 관점의 선행 loss 설계 비교

- 작성일: 2026-09-10
- task_id: `PHD-PRESERVATION-REJECTION-LOSS-REVIEW-20260910`
- 상태: `LITERATURE_DESIGN_REVIEW / NO_METHOD_SELECTED`
- scientific_verdict: null
- 범위: 원문·공식 공개 소스·기존 문서 확인과 별도 분석 작성. 새 학습·추론·렌더·재구성·방법 실험 없음.

## 1. 이 관점으로 무엇을 파악할 수 있는가

**연구별 loss를 도입 목적과 작동 방식으로 읽으면, 유효한 정보를 유지하고 부정확한 정보의 영향을 억제하려는 설계를 비교할 수 있다.** 분석 단위는 `보존할 정보 → 부정확할 수 있는 요구 → 유효성의 근거 → loss·제약의 작동 → 남겨둔 복원 근거 → 성공과 잔여`다. Loss 식에 어떤 target을 넣는지만 아니라 적용 영역·가중·보정 변수·gradient의 전달 대상을 함께 기록한다.

여기서 배제는 감독을 0으로 만드는 경우뿐 아니라 감쇠, robust 비용, 편향 분리, 특정 변수로의 gradient 차단을 포함한다. 감독의 배제와 이미 존재하는 표면의 삭제는 구별한다. 유효 정보의 보존도 원자료 파일의 유지, 감독의 유지, 최종 표면의 보존이 서로 같지 않다.

현재 영상의 반사·조명 변화는 외관에는 실제 정보이면서 기하 위치를 정하는 데에는 불안정한 근거일 수 있다. 따라서 영상 전체를 좋은/나쁜 소스로 고정하지 않는다. 기존 기하 O/X × 영상 O/X의 네 조건은 위치·기하 성분·목표 해상도별 조건으로 유지하며, 영상 O와 파생 depth/normal의 정확성을 동일시하지 않는다.

아래의 목적과 구현은 문헌 사실이고, 독립 기존 기하에 옮길 때의 충분성은 별도 연구 질문이다. 모든 방법이 두 소스의 정확성을 대칭적으로 판정하거나, 모든 잘못된 정보를 이미 제거한다는 뜻은 아니다. Normal loss 우선 도입 계획도 아니다.

## 2. 입력 종류와 선별 이유

| 연구 | 원방법의 입력과 결과 | 이번 비교에 포함하는 이유 |
|---|---|---|
| GeoGS | 정합된 LoD2 + 현재 posed RGB → Gaussian 장면·mesh | 기존 구조의 보호와 영상 depth 기반 정제를 직접 결합 |
| EnerGS | 부분 LiDAR 기하 + posed RGB → Gaussian 장면 | 유효하다고 전제한 센서 구조를 photometric gradient로부터 보호하는 변수·energy 설계 |
| CL-Splats | 과거 외관까지 학습된 3DGS + 현재 RGB/pose → 갱신 3DGS | 기존 장면의 비변경 부분 보존과 변경 부분 수정의 직접 비교 후보 |
| ACMP | posed RGB → 영상 대응에서 얻은 평면 prior → depth·점군 | 영상의 직접 대응 비용과 구조 prior 호환성을 함께 평가하는 기존 원리 |
| AGS-Mesh | 동시 RGB-D 센서 depth + 영상 예측 normal → GS·mesh | 두 종류의 기하 감독을 상호 검사하고 loss의 사용을 조절 |
| NeuRIS | posed RGB + 영상 예측 normal → SDF 표면 | 현재 영상의 다중뷰 일관성으로 기하 감독의 사용을 판단 |
| ND-SDF | posed RGB + 영상 예측 depth/normal → SDF 표면 | 부정확한 감독을 보정하면서 유효한 원감독의 제약도 유지 |
| DebSDF | posed RGB + 영상 예측 depth/normal → SDF 표면 | 감독 filtering과 세부를 학습할 표집·평활화·렌더링 조건을 함께 설계 |
| CoMe | posed RGB → GS·mesh | 현재 영상 잔차의 영향을 조절하면서 외관 정보와 기하 제약을 함께 유지 |

GeoGS 이외의 모든 prior를 기구축 ALS/LoD와 같은 입력으로 부르지 않는다. 특히 영상 예측 prior의 공통 편향, 동시 센서의 노이즈, 독립 자산의 위치·형상·시간 차이는 다르다. Native 알고리즘 비교와 GeoGS에 원리를 도입하는 비교도 구별한다.

## 3. 연구별 loss의 목적과 보존·배제 작동

### 3.1 GeoGS — 구조 기준을 유지하며 영상 기하와 외관 정제의 요구를 조절

**목적:** 희소 영상의 기하 모호성을 LoD 구조로 줄이고, LoD가 생략한 형상은 영상 depth로 보완하며 외관 정제의 자유도를 확보한다.

- **Loss:** prior raycast depth와 합성 depth의 metric L1을 anchor에서 강하게 사용하고 refinement에서도 작게 남긴다. Refinement에 DA3 depth L1과 RGB L1+DSSIM을 함께 사용한다. 논문 식16은 `L_refine = L_2DGS + λ_lod L_lod + λ_vis(t) L_vis`다.
- **보존:** prior와 가까운 Gaussian의 위치·회전·크기 gradient를 감쇠하고 생성/삭제를 제한한다. 작은 prior loss는 기존 구조로부터의 drift를 억제한다. 이 보호는 loss의 계수와 별도다.
- **억제·완화:** 깊이가 안정되고 RGB loss가 개선되는 추세에서 DA3의 공통 가중치를 낮춰 과도한 기하 감독을 완화한다. 원문의 binary valid mask와 공개 코드의 optional DA3 confidence는 서로 다른 제어다.
- **유효성의 근거:** LoD를 구조 기준으로 쓰는 가정, prior 근접성, 학습 loss 추세다. 현재 관측으로 매 위치의 LoD 정오를 판정하는 장치는 아니다. DA3를 완화해도 RGB·prior·기반 정규화가 남는다.
- **확인된 성공/범위:** 원문 Table6은 DA3·보호·adaptive의 결합 효과를 보인다. 우리 P1/P2에서 같은 DA3·보호에 prior 가중만 낮춰 수정이 증가한 결과는 이 loss 요구의 중요성을 뒷받침한다. 그렇다고 prior가 모든 잔여의 유일 원인은 아니다.

근거: [출판 원문 §§3.3–3.4·Table6](/home/innopam/.codex/attachments/74f36af2-99b5-411a-93e5-7fa2ce39fe8d/1-s2.0-S0924271626003588-main.pdf), [공식 train.py](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L805), [controller](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L879). 실제 ALS 적용판의 native confidence는 비활성이며 P1/P2 `.005/.0005` 비교의 기록된 DA3 가중은 모두 `.05`다. 논문상 adaptive의 존재로 실제 감쇠를 추정하지 않는다. 실제 normal 항은 외부 normal target이 아닌 자기일관성이며 distortion 가중은 0이었다. [실행과 보호 감사](../geogs_causal_followup_v1/MASK_DESIGN_AUDIT_ko_v1.md).

### 3.2 EnerGS — 신뢰한 기하 제약을 영상 적합이 상쇄하지 않도록 갱신 경로를 분리

**목적:** 부분 센서 기하가 있는 곳은 유지하고, RGB를 잘 맞추지만 센서상 빈 공간에 놓이는 Gaussian을 억제한다.

- **Energy·loss:** occupied 표면으로의 attraction, free 공간의 barrier, unknown 영역의 약한 energy를 구성한다. RGB L1+DSSIM과 별개로 Gaussian 중심은 기하 energy로 이동시키고, photometric gradient의 중심 전달은 차단한다. 영상은 covariance·opacity·외관과 생성 경로에 영향을 준다.
- **보존·배제:** trusted occupied/free를 위배하는 위치가 좋은 RGB 적합만으로 유지되는 것을 제한한다. Unknown에는 더 약한 제약을 두어 결손 보완을 허용한다.
- **유효성의 근거:** occupied/free 센서 정보가 신뢰 가능하다는 입력 가정이다. 틀린 prior를 영상으로 찾아 배제하는 대칭적 설계로 해석하지 않는다. 코드의 선택적 photometric/coverage gate와 생성 경로가 있으므로 영상의 모든 기하 영향을 차단한다고도 쓰지 않는다.
- **성공/범위:** 저자는 geometric violation 감소를 보고한다. 기구축 prior의 trusted 정보 자체가 현재 틀린 상황에서의 교정 능력은 별도 검증 질문이다. LoD/DSM에서 LiDAR 관측 ray와 같은 free-space 정보를 얻는다고 가정하지 않는다.

근거: [원문 §§3–5](https://arxiv.org/html/2604.26238v1), [공식 geometric_energy.py](https://github.com/ucla-mobility/EnerGS/blob/a222ed59b05a56eecf7b7199e02eb80bcb288775/energs/geometric_energy.py#L252), [train_energs.py](https://github.com/ucla-mobility/EnerGS/blob/a222ed59b05a56eecf7b7199e02eb80bcb288775/train_energs.py#L675). 이번에는 trusted 가정과 energy/gradient 경로를 확인했으며 이론 보장의 가정을 독립적으로 증명한 것은 아니다.

### 3.3 CL-Splats — 현재 RGB loss의 수정 대상을 제한하여 기존 장면 보존

**목적:** 새 관측에서 바뀐 부분을 갱신하면서, 새 시선의 부족으로 비변경 장면이 손상되는 것을 막는다.

- **Loss·제약:** 과거 렌더와 현재 영상의 특징 차이를 2D 변경 mask와 3D 투표로 연결한다. 현재 RGB에 photometric loss를 적용하면서 변경 Gaussian만 최적화한다. 비변경 구조도 렌더에는 남겨 가림·경계 관계를 유지한다.
- **보존·배제:** 보존의 핵심은 추가 보존 loss보다 비변경 Gaussian의 속성 고정과 갱신 범위 제한이다. 현재 공개 코드는 L1+DSSIM, inactive gradient 및 Adam moment 차단을 사용한다. 선택적 sphere-bound loss는 기본 가중이 0이므로 핵심 활성 loss로 일반화하지 않는다.
- **유효성의 근거:** 변화 검출과 3D 집계다. 변화 없음은 원기하가 정확하다는 검증과 같지 않다. 무색 ALS/LoD에는 과거 외관 렌더라는 입력이 직접 존재하지 않는다.
- **성공/잔여:** 비변경 배경을 보호하지 않을 때의 손상은 완성법이 해결한 ablation이다. 완성법에서도 얇은 구조의 변경 영역을 과소 검출하면 필요한 수정이 제한된다.

근거: [원문 §3·§4.2·§9.2/Fig12](https://arxiv.org/html/2506.21117v2), [공개 trainer.py](https://github.com/jan-ackermann/cl-splats/blob/587fffc207f9c7cbb348f35e6d1d223d007eab69/clsplats/trainer.py#L436), [보호 코드](https://github.com/jan-ackermann/cl-splats/blob/587fffc207f9c7cbb348f35e6d1d223d007eab69/clsplats/representation/cl_gaussians.py#L362). **구현 범위:** [공식 README](https://github.com/jan-ackermann/cl-splats/blob/587fffc207f9c7cbb348f35e6d1d223d007eab69/README.md#L337)는 공개 코드가 재구현이며 원논문 구현과 차이가 있을 수 있다고 명시한다. 이번 확인을 원논문 kernel·성능 재현 검증으로 확대하지 않는다.

### 3.4 ACMP — 영상 대응과 구조 prior가 같은 깊이 가설을 함께 평가

**목적:** 영상 대응이 약한 곳은 평면 prior로 보완하고, 평면이 틀린 경계·비평면 부위는 영상 근거로 수정한다.

- **비용함수:** 다중뷰 photometric cost와 prior 평면에 대한 깊이·방향 호환 확률을 결합해 후보를 평가한다. 영상 비용이 깊이 후보를 잘 구별하는 곳에서는 영상이 수정을 유도하고, 구별이 약한 곳에서는 prior가 도움이 되는 설계다. 이후 재투영 오차를 절단한 다중뷰 geometric cost로 추가 오류를 줄인다.
- **보존·배제:** 평면 prior의 유효한 지지를 남기되, 유한한 호환 비용과 영상 대응으로 prior에서 벗어난 후보도 선택할 수 있다. 가림에 의한 큰 재투영 잔차의 영향을 제한한다.
- **유효성의 근거:** credible 영상 대응, 후보의 patch 일치, 시점 선택·재투영 관계다. 평면 prior는 해당 영상에서 만들어지며 독립 기존 자산은 아니다.
- **성공/범위:** 원문은 무텍스처 완전성과 prior 오류 수정의 결합을 보인다. 영상의 깊이 구별력이 실제 약하거나 prior 가정이 맞지 않는 우리 조건에서의 충분성은 별도다. GS에 이미 구현된 loss가 아니라 PatchMatch 가설 선택 비용이다.

근거: [원문 식7·13 및 Algorithm1](https://cdn.aaai.org/ojs/6940/6940-13-10169-1-10-20200525.pdf), [공식 ACMP.cu](https://github.com/GhiXu/ACMP/blob/574c8e078b6f7bd93237bd180d46f5adf1169a19/ACMP.cu#L599).

### 3.5 AGS-Mesh — 위치·방향 감독의 상보성을 사용하고 불일치 감독을 거름

**목적:** sensor depth의 metric 위치와 예측 normal의 방향 정보를 활용하면서, 경계·세부의 부정확한 depth와 normal 감독을 억제한다.

- **Loss:** depth L1과 normal L1을 RGB·기반 기하 정규화와 결합한다. 외부 normal 감독은 렌더 깊이에서 계산한 normal에 적용하여 표면 기하로 전달한다.
- **보존·배제:** 사전 DNC는 sensor-depth 유래 normal과 예측 normal의 불일치로 depth 감독을 거른다. 학습 중 ANR는 현재 기하와 예측 normal을 비교해 normal 감독 사용을 갱신한다. 초기 감독 뒤 적응 제어를 적용하며 RGB와 남은 기하 감독을 유지한다.
- **유효성의 근거:** 두 기하 cue 또는 현재 재구성과의 방향 일치다. 현재 모델을 기준으로 한 ANR는 다시 포함할 수 있는 경로를 가지며 NeuRIS의 누적 기각과 다르다.
- **성공/범위:** Table3의 DNC·ANR·추출 누적 개선을 인정한다. 방향 일치가 절대 위치의 정확성을 보장하지 않는다는 것은 검사에 대한 우리 추론이며, 완성법 전체가 위치 오류를 수정하지 못한다는 관측 사실은 아니다.

근거: [원문 §§4–5/Table3](https://arxiv.org/html/2411.19271v2), [공식 train.py](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/train.py#L127), [DNC](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/depth_normal_consistency.py#L99).

### 3.6 NeuRIS — 현재 영상의 다중뷰 검사로 예측 기하 감독을 선택

**목적:** 무텍스처 면에는 normal prior를 유지하고, 부정확한 prior가 얇은 구조·세부를 강제하는 영향을 줄인다.

- **Loss:** RGB L1·normal 감독·Eikonal을 결합한다. 논문 식9의 normal residual은 벡터 L1이다. **확인한 공식 pin의 실제 normal loss는 정규화 내적의 arccos를 평균한 각도오차**다. 원문 식과 코드의 이 차이를 보존한다.
- **보존·배제:** 현재 기하에서 다중뷰 patch NCC를 계산해 normal 감독의 사용 mask를 만든다. NCC 자체를 이 경로의 미분 가능한 loss로 최소화하는 것은 아니다. 코드에는 이전 기각 이력과 normal 차이 조건도 있다. 기각된 감독 대신 RGB와 SDF 제약이 남는다.
- **유효성의 근거:** 현재 재구성이 여러 영상과 일치하는가이다. 현재 모델의 오류로 정확한 prior가 기각될 가능성은 별도 가설이며, 논문이 해당 실패 빈도를 입증한 것은 아니다.
- **성공/범위:** normal 도입과 geometric check의 추가 개선, 평면과 얇은 구조의 동시 복원은 완성법의 성과다. 그 원리를 prior/DA3 depth에 사용하려면 검사 대상과 잔차의 의미를 다시 정해야 한다.

근거: [원문 §§3–4/Table3](https://arxiv.org/html/2206.13597v2), [공식 loss.py](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/models/loss.py#L192), [각도오차 함수](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/utils/utils_training.py#L19), [NCC와 기각 이력](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/exp_runner.py#L329). 이전 요약에서 논문 L1과 코드 각도오차를 구분하지 않은 부분은 이번 기록의 구분을 따른다.

### 3.7 ND-SDF — 감독의 편향을 허용하면서 유효한 원래 제약을 유지

**목적:** 잘못된 normal target의 강제로 세부가 사라지는 것을 줄이고, 자유 보정 때문에 유효 평면 제약도 사라지는 것을 막는다.

- **Loss:** 원래 렌더 normal과 학습한 회전으로 변환한 렌더 normal을 각각 고정 예측 prior와 비교하는 L1+cosine 항을 적응적으로 결합한다. 입력 target 파일을 새로 예측하는 방법은 아니다.
- **보존·편향 처리:** 편차가 작은 곳은 원래 normal 제약을 유지하고 큰 곳은 회전된 normal의 비교 비중을 높인다. 같은 편차로 depth 감독·RGB·표집·부분 rendering 보정도 조절한다. 단순 제외 후 끝나는 알고리즘이 아니다.
- **유효성의 근거:** 학습한 normal 편차다. 가중치 계산에서 gradient를 분리하며 원 normal 항을 남긴다. 법선 편차로 깊이를 함께 다루는 논리는 같은 예측기의 공통 편향과 관련되며 독립 metric ALS 깊이에는 그대로 성립하지 않는다.
- **성공/범위:** 회전만 허용한 ablation의 평면 주름은 adaptive prior를 추가해 개선했다. 이를 완성법 잔여로 인용하지 않는다. DA3 metric depth를 보정하는 구체식이나 외부 자산의 정오 판정은 이 논문에서 제공하지 않는다.

근거: [원문 §3·Table6·Appendix B.2](https://arxiv.org/html/2408.12598v3), [공식 loss.py](https://github.com/zju3dv/ND-SDF/blob/f58f29466a5f43e80dedb0cd155f57dae7569347/models/loss.py#L302).

### 3.8 DebSDF — 부정확한 감독을 약화하고 실제 세부 복원의 학습 조건도 확보

**목적:** 잘못된 단안 감독을 억제한 뒤에도 남는 표집 부족·과도한 평활화·렌더링 편향을 함께 처리한다.

- **Loss:** 공개 구현의 depth 항은 scale/shift 정합 뒤 `log U_d + abs(r_d)/U_d`, normal 항은 성분별 `log U_n² + r_n²/U_n²` 형태다. 높은 불확실성에서 직접 geometry residual의 gradient를 차단하되 uncertainty 학습은 계속한다. Log 항은 불확실성을 키우기만 하여 감독을 회피하는 퇴화를 억제한다.
- **보존·배제 후 복원:** 낮은 불확실성의 기하 감독을 유지한다. 어려운 영역에는 RGB 기반 학습 표본을 더 배분하고 smoothness를 완화한다. 곡률을 고려한 SDF-density 변환까지 결합해 세부가 표현되는 조건을 마련한다. 직접 residual 차단을 모든 간접 기하 gradient의 제거로 확대하지 않는다.
- **유효성의 근거:** 현재 모델과 시점별 prior의 불일치에서 학습한 불확실성이다. **저자는 다수 prior가 틀리면 틀린 prior에 낮은 uncertainty, 맞는 prior에 높은 uncertainty가 나올 수 있음을 명시한다.** 저자는 RGB 학습이 진행되며 이런 경우가 줄어든다고 설명하지만 완전한 filtering 보장은 아니다. 이는 저자 분석이며 모든 데이터의 관측 실패율은 아니다.
- **성공/잔여:** TableIV는 filtering 이후 표집·smoothness·변환까지의 누적 개선을 보인다. Prior 품질·감독 해상도 한계가 남는다. 해결된 중간 ablation과 저자 인정 한계를 구별한다.

근거: [원문 §III-B–E·TableIV·§V](https://arxiv.org/html/2308.15536v3), [공식 loss.py](https://github.com/DavidXu-JJ/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/model/loss.py#L238). 과거 문서에서 공통 오답의 uncertainty 문제를 우리 질문으로만 적은 부분에 대해, 원문 §III-B에 해당 가능성의 저자 설명이 있음을 이번에 확인했다.

### 3.9 CoMe — 외관 정보를 사용하면서 기하에 불리한 photometric 요구 완화

**목적:** 시선 의존 외관을 맞추기 위해 잘못된 기하와 과도한 Gaussian을 만드는 경로를 줄인다.

- **Loss:** `C L_rgb − β log C`로 학습 confidence와 RGB 손실을 결합한다. Log 항은 confidence를 0으로 내려 모든 RGB 요구를 없애는 해를 억제한다. 기하 loss는 이 confidence로 함께 약화하지 않는다.
- **보존·배제:** 외관 보정된 영상으로 L1과 D-SSIM luminance를 비교하고, contrast/structure에는 원 렌더를 사용한다. 실제 조명·외관 변동의 영향을 처리하면서 구조 단서를 남기려는 설계다. Color/normal variance 제약과 confidence 기반 생성 제어도 결합한다.
- **유효성의 근거:** 현재 photometric residual과 학습 confidence다. Confidence는 정확성 인증이 아니며 낮은 confidence가 관측 사진 전체를 폐기한다는 뜻도 아니다.
- **성공/범위:** 원문은 외관·confidence·생성·variance의 효과를 비교한다. 모든 지표에서 각 요소가 단조 개선하는 것은 아니며 미관측 구멍도 남는다. 외부 기구축 기하의 보존·수정은 원방법의 직접 평가 범위가 아니다.

근거: [원문 §§3.2–3.4·Tables3–5·§5](https://arxiv.org/html/2603.24725v2), [공식 confidence loss](https://github.com/r4dl/CoMe/blob/caf62f6402dd82a301f7aa9d43350209f7309911/train.py#L203), [appearance loss](https://github.com/r4dl/CoMe/blob/caf62f6402dd82a301f7aa9d43350209f7309911/scene/appearance_network.py#L261).

## 4. 이 비교에서 드러나는 차이와 GeoGS에 남길 질문

각 연구의 차이는 loss의 개수보다 **무엇을 신뢰하는가, 그 신뢰를 어떻게 얻는가, 잘못된 요구를 약화한 뒤 무엇을 남기는가**에 있다. GeoGS·EnerGS처럼 기하의 신뢰를 입력 가정으로 강하게 사용하는 설계, AGS·NeuRIS처럼 일관성으로 검사하는 설계, DebSDF·CoMe처럼 불확실성을 학습하는 설계, ND-SDF처럼 편향을 설명하면서 원제약을 남기는 설계가 있다. 한 연구가 여러 방식을 함께 쓸 수 있다.

| GeoGS 기존 결과와 연결할 질문 | 먼저 검토할 기존 원리 | 아직 기여로 확정할 수 없는 이유 |
|---|---|---|
| P1/P2에서 prior와 DA3의 유효한 요구를 각각 유지하고 부정확한 요구만 줄일 수 있는가? | 기존 prior 가중·보호, optional DA3 confidence, AGS/NeuRIS형 일관성 반영 | 국소 weighting·mask 자체는 기존 원리이며 대리 신호가 원모델 오류와 감독 오류를 혼동할 수 있음 |
| P1처럼 DA3가 수정 방향은 주지만 충분한 깊이를 제공하지 못하면 무엇이 남은 수정을 지지하는가? | ACMP형 직접 영상 관계, 기존 깊이 보정, ND형 제약된 편향 처리의 적합한 변형 | 감독을 약화하는 것만으로 맞는 depth가 새로 생기지 않음. 추가 정보의 이득과 새로운 규칙의 이득을 구분해야 함 |
| P2의 유효 골 정보와 이미 성공한 큰 형상 수정, P3의 지붕·측벽을 함께 유지할 수 있는가? | Loss와 변수 보호의 분리, CL-Splats형 제한 갱신, CoMe형 외관 처리, 적절한 기존 표현·추출 제어 | Anchor부터 불완전한 정보를 anchor 고정만으로 회복할 수 없음. 감독 배제와 유효 최종 표면 보존은 별도 검증 |

이 표는 모든 원인을 입증할 때까지 설계를 미루는 관문이 아니다. 각 가설에 맞는 기존 loss·제약을 먼저 비교 대상으로 구체화하고, 동일 입력·anchor·감독 정보·정합·추출·계산 예산에서 충분성을 확인할 최소 실험계획으로 연결한다. Prior 깊이 가중과 구조 보호는 독립 제어로 둔다. 같은 영역의 필요한 보정과 유효 구조 손상, 정확도·완전성·현재성·관측 가능한 세부·외관·비용을 따로 평가한다. 기존 방법의 성공과 제안법의 악화도 포함한다.

보존·배제라는 공통 목적이 있다는 이유로 우리 연구의 차별성을 부정하지 않으며, 그 목적을 함께 요구한다는 이유로 신규성을 확정하지도 않는다. 남는 중요한 부족과 기존 설계의 가정을 연결하고, 기존 제어의 조정·도입으로 충분하지 않은 경우를 겨냥한 추정·제약 원리가 방법 기여 후보가 된다.

## 5. 자료·실행 경계

- 앞선 [결과 기반 refinement 설계](REFINEMENT_RESULT_LED_DESIGN_ko_v1.md), [전체 알고리즘 분석](FULL_METHOD_DESIGN_AND_RESIDUALS_ko_v1.md)은 맥락과 색인으로 보존한다. 이번 문서는 loss 목적·작동 관점의 별도 정리다.
- GaussianUpdate도 기존 장면의 외관·기하 수정 분리를 다루는 보조 문헌이다. [원문](https://arxiv.org/html/2508.08867v1)과 [공식 프로젝트](https://zju3dv.github.io/GaussianUpdate/)는 확인했지만 이번 검색에서 공식 학습 구현을 찾지 못했으므로 구현 대조 완료 표에 포함하지 않았다. 문헌 실패로 해석하지 않는다.
- 공개 코드 pin의 정적 경로 확인은 논문 실행 설정·성능의 재현이 아니다. 특히 CL-Splats의 공개 재구현, NeuRIS의 논문/코드 normal residual 차이를 명시했다.
- 문헌 원문은 웹 또는 이미 보존된 GeoGS 전문 텍스트로 읽고, 공개 코드는 읽기만 했다. Host에서 프로젝트 의존성·도구를 실행하지 않았다. `/tmp` 전문 색인 검색 중 다른 서비스 소유 경로의 permission 오류가 있었으며 우회·권한 변경 없이 확인 가능한 기존 전문 파일만 읽었다.
- 기존 코드·문서·실험·서비스는 수정하지 않았다. GT는 평가 전용이고 `scientific_verdict: null`을 유지한다.
