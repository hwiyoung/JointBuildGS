# 감독 신호·loss 중심 설계 분석의 검증과 최소 비교안

- 작성일: 2026-09-10
- task_id: `PHD-SUPERVISION-LOSS-DESIGN-BASIS-20260910`
- 상태: `LITERATURE_VERIFIED_DESIGN_FRAMEWORK / PROVISIONAL_METHOD_CANDIDATES`
- scientific_verdict: null
- 범위: 원문·공식 구현·기존 실행 기록의 읽기와 별도 문서 작성. 새 학습·추론·렌더·재구성·방법 실험 없음.

## 1. 검증 결론과 적용할 분석 단위

**설계 의도를 감독 신호와 loss 선택을 중심으로 분석하는 것은 현재 연구에 적합하다.** 어떤 정보를 복원의 근거로 삼고, 그 정보를 어떤 오차·신뢰 가정 아래 기하에 반영하는지 설명할 수 있기 때문이다. 선행연구에서도 기하 cue의 추가/제거, 같은 cue의 선별·가중, 보정된 예측과 원감독 사이의 손실 구성은 실제 설계·ablation의 단위다.

이 결론은 두 범주가 모든 알고리즘을 독립적으로 완전 분해한다는 정리가 아니다. **방법 설계와 공정한 비교에 유용한 분석 틀이라는 판단**이다. 손실이 학습하는 신뢰도·보정 변수가 다시 감독의 사용을 바꿀 수 있으므로 두 축의 연결을 기록한다. 표현·보호·표집·생성/삭제는 해당 loss가 실제로 작용하는 조건으로 함께 명시한다.

사용자가 확인한 진행 의도는 다음과 같다.

> 연구 목적과 입력 조건 → 선행연구의 감독 신호·loss 선택 이유와 결합 → 완성법의 성공 및 남는 가정 → 우리 조건에 도입·변경할 후보 → 최소 비교와 기각 조건.

골 소실·능선 손상 등은 설계 가설의 효과와 부작용을 검증할 평가 항목으로 둔다. 모든 사후 원인을 완전히 입증해야 설계를 시작할 수 있다는 관문을 두지 않는다. 기존 결과는 후보를 구체화하고 반증할 근거이며, 관측된 현상을 무시한다는 뜻도 아니다.

기존 기하 O/X × 현재 영상 O/X의 네 입력 조건을 유지한다. O/X는 같은 위치·기하 성분·목표 해상도의 유효성을 뜻한다. 영상 O와 파생 depth/normal의 정확성을 동일시하지 않는다. 세부·외관의 관측 가능성을 따로 설명하며 P1/P2/P3 전체를 한 case로 고정하지 않는다.

## 2. 두 축에 기록할 정확한 내용

| 중심 축 | 기록할 내용 | 구분할 예 |
|---|---|---|
| **감독 신호: 무엇을 근거로 삼는가** | target 또는 관측 관계, 출처·좌표·단위·해상도·가시성, 신뢰·제어 신호, 추정·갱신 시점과 가정 | prior depth/DA3 depth/normal/RGB는 맞출 값 또는 관측이다. NCC·normal disagreement·uncertainty·loss 추세는 주로 사용 여부·강도를 정하는 신호다. |
| **loss: 그 근거를 어떤 요구로 반영하는가** | 비교할 예측과 target/관계, 오차 함수와 정규화, mask/weight/schedule, 보정 변수, 보정·신뢰도 자체의 제약, gradient가 향하는 변수 | 같은 depth라도 metric 오차와 scale/shift를 제거한 오차는 다른 요구다. 같은 normal이라도 그대로 맞춤, 일부 기각, 보정 관계를 학습하며 맞춤은 다르다. |

각 항에는 **도입 목적 → 가정 → 실제 작용 변수 → 다른 항과의 관계 → 기대 효과/실패 조건**을 붙인다. Loss 이름의 목록이나 가중치 숫자만으로 설계 의도를 설명하지 않는다. 정규화는 외부 target이 없는 경우에도 구조에 대한 가정을 표현한다.

신뢰도는 정답 라벨이 아니다. 예를 들어 모델과의 불일치에는 감독 오류와 아직 수정되지 않은 모델 오류가 함께 들어갈 수 있다. 이 구별은 신뢰도 모듈을 필수로 넣으라는 요구가 아니라, 해당 신호를 택한 설계 가정을 명시하라는 뜻이다.

## 3. 실제 선행 설계와의 대조

아래는 각 완성법에서 두 축이 어떻게 연결되는지 보여주는 발췌다. 일부 항만 이식한 결과는 원방법 전체의 재현으로 부르지 않는다. 완성법의 더 상세한 성과·잔여는 [전체 설계 분석](FULL_METHOD_DESIGN_AND_RESIDUALS_ko_v1.md)에 있다.

### 3.0 분석 단위를 직접 확인한 MonoSDF와 NeuRIS

**MonoSDF**는 RGB의 모호성을 보완하기 위해 단안 depth/normal을 선택하고, 단안 깊이의 scale/shift 모호성을 처리하는 loss와 normal L1·cosine loss로 기하에 반영한다. Table2(a)의 `No Cues / Only Depth / Only Normal / Both Cues`는 감독 정보 선택이 실제 비교 단위임을 보여준다. Table1의 표현 비교는 별도다. 이것은 cue의 효용을 검사한 것이며 L1이 다른 모든 residual보다 좋다는 증명은 아니다. [원문 §3.3/§4.1/Table2](https://arxiv.org/html/2206.00665v2), [공식 loss.py L118–162·188–241](https://github.com/autonomousvision/monosdf/blob/12513009cd20a08b35ddc2c55a7e42da2c7baf43/code/model/loss.py#L118).

**NeuRIS**는 normal prior의 도움을 받으면서 부정확한 prior가 세부를 강제하지 않게 하려고, 현재 표면에서 계산한 다중뷰 patch NCC를 normal 감독의 선택에 사용한다. Table3은 `NeuS / + normal prior / + geometric check`를 나눠 감독 정보와 사용 규칙의 효과를 비교한다. NCC는 이 경로에서 직접 최소화하는 photometric loss가 아니라 gate의 근거다. 공식 코드에는 `no_grad` NCC, 이전 기각 상태, 현재 normal 차이가 함께 들어간다. 이를 NCC 하나만의 보편적 신뢰도로 요약하지 않는다. [원문 §3/§4.3/Table3](https://arxiv.org/html/2206.13597v2), [공식 exp_runner.py L329–396](https://github.com/jiepengwang/NeuRIS/blob/fab2cc4ca45847fbee7490e978d3c60c582123b1/exp_runner.py#L329).

두 방법은 독립 기존 geometry를 수정하는 직접 경쟁과 입력이 같지 않지만, 감독 선택·감독 사용의 분석 단위를 검증하고 영상 기하 감독의 도입 후보를 정하는 근거로 관련된다. 각 논문의 전체 구현·학습 데이터 조건을 GeoGS의 구성요소 이식과 구분한다.

### 3.1 GeoGS: 기준 구조와 영상 기하를 함께 유지하며 외관 정제의 자유도 조절

- **선택 이유:** 희소 영상의 불안정한 초기 기하를 기존 LoD 구조로 확보하고, 조밀한 영상 depth로 세부와 주변을 보완한다.
- **감독 신호:** RGB, 고정 prior raycast depth, offline DA3 depth. DA3 loss의 안정성과 RGB loss의 개선 추세는 시간 가변 가중의 제어 신호다. 선택적 DA3 confidence는 이 공통 controller와 별개다.
- **Loss와 연결:** anchor의 prior 깊이 요구 뒤 refinement에서 작은 prior loss와 DA3/RGB 항을 함께 사용한다. DA3 가중을 완화하면서 구조 보호를 남긴다. 깊이 가중과 위치·회전·크기 gradient 및 생성/삭제 보호는 독립 제어다.
- **확인된 의미:** Table6의 전체 구성과 제거 비교는 요소들의 조건부 기여를 뒷받침한다. 모든 지역의 감독 타당성을 판단하는 최선의 규칙이라는 증명은 아니다.
- **우리 설계 질문:** 기존 공통 제어를 유지하거나 이미 시험한 prior 제어를 사용했을 때, 관측별 감독 반영 또는 감독 편향 보정을 더할 근거가 있는가? 현재 GeoGS가 이를 실패했다고 미리 판정하지 않는다.

근거: [첨부 출판 전문 §§3–5](/home/innopam/.codex/attachments/74f36af2-99b5-411a-93e5-7fa2ce39fe8d/1-s2.0-S0924271626003588-main.pdf), [공식 train.py](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py). P1/P2/P3는 ALS 입력 적응판이며 논문 LoD2 입력 재현과 구분한다.

### 3.2 AGS-Mesh: 기하 감독의 불일치에 따라 깊이·법선 요구 조절

- **선택 이유:** sensor depth의 위치 정보와 단안 normal의 방향 정보를 함께 사용하되, 세부·경계의 depth 오류와 normal의 불일치가 복원을 강제하지 않게 한다.
- **감독 신호:** sensor depth, predicted normal, RGB. Depth-derived normal과 predicted normal의 각도는 DNC 신호이며, 현재 rendered-depth normal과 predicted normal의 비교는 ANR 신호다.
- **Loss와 연결:** DNC는 depth 감독 mask, ANR는 normal 감독 mask에 작용한다. 현재 기하로 ANR를 재계산하는 경로와 사전 DNC를 구분한다. 생성과 추출도 전체 알고리즘에 포함된다.
- **성과의 범위:** Table3은 depth/normal 추가와 DNC/ANR·추출의 누적 효과를 보여준다. 특정 mask 한 개가 전체 성과를 단독으로 만든다는 비교는 아니다.
- **우리 적용 가정:** prior mesh의 raycast depth는 실내 depth sensor의 관측과 오류·가시성이 다르다. 각도 일치는 절대 위치의 정확성을 보증하지 않는다. 독립 기하를 넣은 adaptation에서 어떤 신호를 어느 loss에 적용할지 다시 명시한다.

근거: [원문 §§4–5/Table3](https://arxiv.org/html/2411.19271v2), [공식 train.py](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/train.py), [DNC 코드](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/depth_normal_consistency.py).

**도입 계획에서 바로 구별할 사실:** GeoGS 기존 normal loss는 `rend_normal`과 `surf_normal` 사이의 자기일관성이며 외부 pretrained normal target과의 손실이 아니다. AGS ANR를 도입하려면 예측 normal 정보와 해당 감독 손실을 추가하는 효과부터 구분한다. AGS §4.2는 법선을 rendered depth에서 계산해 geometry로 gradient가 전달되도록 하는 이유를 설명한다. 따라서 우리 기준에서도 단순히 Gaussian의 독립 방향 변수만 맞추는 항과 혼동하지 않는다. [GeoGS train.py L821–830](https://github.com/zqlin0521/GeoGS/blob/db40c95c657ec03ff21c83cb99cf39f4e90247a6/train.py#L821), [AGS §4.2 식9](https://arxiv.org/html/2411.19271v2#S4.SS2), [AGS renderer L174–183](https://github.com/XuqianRen/AGS_Mesh/blob/93fda851a20cf0bd5fce642c46da0c83c637165e/gaussian_renderer/__init__.py#L174).

### 3.3 ND-SDF: 보정된 법선 관계와 원래 감독의 제약을 함께 학습

- **선택 이유:** 편향된 normal을 그대로 강제하면 세부가 억제될 수 있지만, 자유롭게 보정하기만 해도 유효 평면의 제약이 약해질 수 있다.
- **감독 신호:** RGB와 단안 depth/normal. 학습한 normal deflection의 각도를 감독 반영의 신호로 사용한다.
- **Loss와 연결:** 기하에서 예측한 normal을 회전해 원 prior normal과 비교하며 원래 normal 손실도 적응적으로 함께 사용한다. 입력 normal 파일 자체를 재추론하는 방법으로 설명하지 않는다. Depth·표집·광도·부분 rendering 보정에도 각도를 연결한다.
- **성과의 범위:** Table6의 자유 보정에서 생긴 평면 문제는 adaptive prior를 추가해 개선한 ablation이다. 이를 완성법의 잔여 실패로 옮기지 않는다.
- **우리 적용 가정:** 같은 단안 추정기의 depth/normal 편향 관계와 독립 metric prior의 위치·방향 오류는 다를 수 있다. Normal 각도로 prior depth까지 함께 제어하는 규칙과, 위치·방향의 근거를 구별하는 규칙을 비교할 질문이 생긴다.

근거: [원문 §3/Table6/Appendix B.2](https://arxiv.org/html/2408.12598v3), [공식 loss.py](https://github.com/zju3dv/ND-SDF/blob/f58f29466a5f43e80dedb0cd155f57dae7569347/models/loss.py), [system.py](https://github.com/zju3dv/ND-SDF/blob/f58f29466a5f43e80dedb0cd155f57dae7569347/models/system.py).

### 3.4 DebSDF: 감독 신뢰와 세부를 허용하는 정규화의 결합

- **선택 이유:** 부정확한 단안 감독을 약화한 뒤에도 표집 부족·평활화·SDF의 렌더링 편향이 세부 학습을 제한할 수 있다.
- **감독 신호:** RGB와 단안 depth/normal, 학습 불확실성.
- **Loss와 연결:** 불확실성에 따른 기하 감독 filtering과 smoothness 조절을 표집·곡률 기반 변환 및 warm-up과 함께 사용한다. Filtering이 uncertainty 학습까지 중단한다는 뜻은 아니다.
- **우리 적용 가정:** 감독 가중만 바꾸는 대비와 필요한 정규화·표집을 연결한 대비를 구분한다. SDF→density 보정을 GS에 그대로 복사하거나, 일부 loss 도입을 DebSDF 전체 재현이라고 하지 않는다.
- **성과의 범위:** 얇은 구조의 중간 ablation 부족은 후속 요소로 개선됐다. 완성법의 prior 품질·해상도 한계를 그 ablation과 구분한다.

근거: [원문 §§III-B–E/TableIV/§V](https://arxiv.org/html/2308.15536v3), [공식 loss.py](https://github.com/DavidXu-JJ/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/model/loss.py), [training driver](https://github.com/DavidXu-JJ/DebSDF/blob/4580c8e1c9872e65f6cb9fc55607162f57ab7a54/code/training/debsdf_train.py).

### 3.5 CoMe: 같은 RGB에서도 비교 성분과 신뢰도 손실을 달리 설계

조명에 민감한 D-SSIM luminance는 appearance 보정된 RGB로, contrast/structure는 원 렌더로 비교한다. 같은 RGB 감독에서도 어떤 성분을 어떻게 비교할지에 연구 의도가 나타나는 사례다. Learned confidence를 곱한 photometric loss에는 음의 log-confidence 항을 함께 두며, confidence를 무조건 낮추는 방향을 제어한다. 신뢰도와 loss는 상호 의존하므로 독립 입력 두 개처럼 설명할 수 없다. Confidence는 densification에도 사용되고 variance loss는 primitive 합성의 모호성을 다룬다. 전체 성과가 모든 장면·지표의 동시 개선이라는 뜻은 아니다.

근거: [원문 §§3.2–3.4/§4.2](https://arxiv.org/html/2603.24725v2), [공식 train.py L187–206](https://github.com/r4dl/CoMe/blob/caf62f6402dd82a301f7aa9d43350209f7309911/train.py#L187). 원 RGB와 관측 외관은 사용할 수 있는 감독이며 이 코드의 `gt_image`를 독립 평가 3D GT와 혼동하지 않는다. 독립 기존 기하의 보존·수정은 구성요소 도입에서 검증할 범위다.

## 4. 이 분석으로 정한 도입 질문과 우선순위

아래 후보는 하나의 대형 모델에 모두 넣을 구성표가 아니다. 같은 문제를 기존 해법으로 풀 수 있는지 구별하기 위한 설계 질문이다.

| 질문·우선도 | 사용할 신호 후보 | Loss 설계에서 정할 것 | 남는 가정과 범위 |
|---|---|---|---|
| **Q1. 관측별 반영이 필요한가? 우선** | 기존 DA3 confidence, AGS식 기하 일관성, 현재 영상의 다중시점 일관성 | fixed target의 어느 항을 mask/연속 가중할지, 근거 부족과 불일치를 어떻게 구분할지, 신호 갱신과 기존 controller의 관계 | 같은 기하와의 불일치만으로 감독 오류를 확정하지 않음. 동일한 신호를 주고 반영 방식만 비교하는 대비도 필요 |
| **Q2. 약화보다 제약된 보정이 필요한가? 우선** | 고정 normal/depth, 관측 일관성, 학습 보정량 | 원감독/보정 관계의 손실, 보정 자유도의 범위와 제약, 기하와 보정 변수가 잔차를 나눠 설명하는 방식 | ND형 기존 원리가 첫 비교. 가중법보다 항상 낫다고 전제하지 않음 |
| **Q3. 위치·방향 감독의 제어 근거를 분리해야 하는가? Q1/Q2와 병행** | Normal 관계와 위치를 지지하는 다중시점/metric evidence를 구별 | Normal 신호로 depth까지 묶는 규칙과, 각 기하 성분의 근거로 해당 loss/보정 자유도를 제어하는 규칙 | 새로운 추정·제약 원리의 후보. 성분을 나누는 것 자체는 신규성이 아니며 기존 분리 가중·보정으로 충분한지 확인 |
| **Q4. 감독 완화와 관련 정규화의 연동이 필요한가? 조건부** | 같은 uncertainty/consistency, RGB | 감독 항만 완화 / 관련 smoothness까지 연동. 필요한 경우 기존 표집을 별도 대비 | DebSDF의 완성 제어를 단순 filtering으로 축소하지 않음. 추가 표집 이득과 loss 이득을 구분 |
| **Q5. 외관 감독의 비교 방식이 구조 손상에 관여하는가? 조건부** | 같은 RGB, appearance 보정, photometric confidence | 기존 appearance 보정/CoMe식 photometric loss를 도입할 범위와 동일 정보 비교 | 구조 수정과 외관 적합이 서로를 대신 설명할 수 있다는 설계 가설. 기존 요소만으로 충분하면 새 기하 controller 필요성 축소 |

후보 문헌은 검토 범위의 경계가 아니다. Predictor 자체의 정보를 개선하는 방법, 다중시점 관계를 직접 손실로 사용하는 방법, metric prior의 위치·방향 제약을 설계하는 방법도 같은 표에 추가할 수 있다. 새로운 문헌은 입력 조건과 도입할 연결의 관련성을 명시한다.

## 5. 질문별 최소 실험계획 — 실행하지 않음

### 5.1 이미 있는 비교를 사용

P1/P2/P3의 주18개는 지역 3 × refinement prior 깊이 `.005/.0005/0` × 보호 `native/release`이며 필수 학습·렌더·1024/512 raw/post 추출을 완료했다. 각 지역의 여섯 조건은 같은 anchor를 공유한다. 이 결과를 기본 구성과 주요 prior 제어의 개발 근거로 사용한다. 새 baseline을 다시 실행해야 설계를 시작할 수 있다는 조건은 없다.

보호 해제는 gradient 감쇠와 생성/삭제 보호를 함께 해제한 대비다. Prior 가중 0에도 초기화·anchor의 prior 영향이 남는다. 보조 반복은 P1/P2 OOM, P3 미실행이므로 실행 간 품질 변동을 입증하지 않는다. SfM 초기화/anchor 생략 등 다른 기존 작업은 별도 계보로 보존한다.

근거: [기존 조건표](../geogs_p1p2p3_v1/EXPERIMENT_PLAN_ko_v1.md#4-비교-조건과-학습량), [완료 범위](../geogs_p1p2p3_v1/EVALUATION_COMPLETION_AMENDMENT_ko_v2.md), [실제 제어 기록](../geogs_p1p2p3_v1/CONTROL_TRAJECTORIES_ko_v1.md#실제-실행과-확인된-제어-차이).

### 5.2 무엇을 바꿨는지 구별하는 대비

| 설계 질문 | 필요한 최소 대비 | 함께 고정할 것 | 기각·축소 조건 |
|---|---|---|---|
| Q1a: 판단 신호가 유용한가? | 기존 공식 confidence/적합한 기존 일관성 신호끼리 같은 반영식으로 비교 | target·정합·초기 구조·loss식·가중 정규화·보호·추출·예산 | 새 신호가 수정–손상 관계를 개선하지 못하면 채택 근거 부족 |
| Q1b: 같은 신호를 어떻게 쓸 것인가? | 동일 신호에서 기존 mask/연속 가중 등 해당 가정에 맞는 두 방식 | 정보·신호 생성 비용·갱신 주기·나머지 loss | 기존 반영 방식으로 충분하면 새 weighting 원리 필요성 축소 |
| Q2: 보정의 추가 가치가 있는가? | 가중 조절 / 기존 ND형 제약된 보정 / 구체화된 제안 보정 규칙 | 사용 가능한 모든 cue·anchor·prior 보호·동일 출력·비교 가능한 예산 | 기존 보정과 차이가 없거나 같은 영역의 유효 구조 손상만 늘면 제안 축소. 제안식이 정의되기 전에는 세 번째 arm을 실행 가능한 계약으로 취급하지 않음 |
| Q3: 근거를 성분별로 쓰는 원리가 필요한가? | 같은 위치·방향 신호 모두 제공 후 기존 공유 제어 / 적절한 기존 분리 제어 / 제안한 제약 규칙 | predictor·정보·계산·표현·변수 수의 영향 분리 | 기존 분리 가중으로 같은 효과면 새 원리 주장 축소. 정보 추가만의 이득이면 그에 맞게 기여 재서술 |
| Q4/Q5: 연결된 기존 요소가 충분한가? | 선택한 감독 제어 고정 후 관련 정규화 또는 외관 loss만 변경 | 한 대비에서 바꾸는 연결을 명시, 표집·생성 변화가 필요하면 별도 대비 | 기존 연동 요소로 해결되면 새로운 복합 모듈보다 그 요소 채택 |

신호와 loss가 함께 학습되는 방법에서는 모든 조합이 의미 있지 않을 수 있다. 예컨대 학습 confidence를 고정 confidence로 바꿨으면서 원 uncertainty 학습 항의 의미가 같다고 가정하지 않는다. **유효한 대응 비교와 필요한 상호작용만** 설계한다. 모든 후보·모든 조합을 전수 실행하는 계획이 아니다.

추가 normal/feature predictor를 사용하면 그것은 같은 RGB에서 왔더라도 추가 감독 정보와 계산이다. 해당 원리의 효과를 비교하는 군에 같은 출력 접근권을 주고, 원 GeoGS와 비교하는 전체 시스템의 정보·비용 증가를 함께 밝힌다. 이미 수행한 결과에 존재하지 않았던 정보를 소급해서 동일 입력이라고 부르지 않는다.

### 5.3 평가와 설계를 연결

각 가설은 같은 물리 영역에서 필요한 수정량과 유효 구조 손상을 함께 평가한다. 정확도·완전성·현재성·관측 가능한 세부·외관·계산량을 분리한다. 골/능선 단면은 관련 가설의 검증 항목이며 그 현상만으로 원인을 확정하지 않는다. Raw/post와 같은 해상도끼리 비교하고 평가 참조의 피복을 표시한다.

P2 저가중의 정성적 형상 개선을 평균 F1 하락으로 부정하지 않는다. P3 저가중의 일반적 악화는 확정되지 않았다. 기존 방법의 성공, 제안법의 악화와 무효과도 포함한다. 개발 결과로 참조에 가장 잘 맞는 값을 골라 배치 가능한 규칙이라고 주장하지 않는다.

GT는 평가 전용이다. 신호·loss·정합·confidence·보정 target·파라미터 선택에 평가 참조를 넣지 않는다. 정보 자체가 부족한 XX에서 loss 추가만으로 현재 형상을 식별할 수 있다고 주장하지 않는다.

### 5.4 먼저 구체화한 normal 감독 비교군

이 표의 표기는 설계용 약칭이며 새로운 실행 ID·승인이 아니다. Normal은 검토를 시작할 구체적인 감독 후보이며 최종 입력을 normal에 고정하지 않는다. 선택 근거는 MonoSDF/AGS/NeuRIS/ND의 확인된 설계 관계와 GeoGS의 기존 외부 normal 감독 부재다.

| 설계용 약칭 | 감독 정보와 loss | 판별할 질문 |
|---|---|---|
| **B0** | 기존 GeoGS ALS 적응판. 기존 여섯 prior 제어 조건을 함께 참조 | 이미 있는 정보·제어로 달성한 수준 |
| **N0** | 같은 RGB에서 생성한 하나의 고정 normal target을 추가하고, rendered depth 유래 normal과 비적응 L1로 비교. 기존 자기일관성 항도 유지 | 외부 normal 정보 자체가 기하를 보완하는가 |
| **N-AGS** | N0와 같은 target·L1에서 AGS ANR식 선택 적용 | 현재 기하와 normal의 일관성에 따른 사용 규칙의 추가 효과 |
| **N-NCC** | N0와 같은 target·잔차에 NeuRIS식 현재 다중뷰 patch 검사에 따른 선택 도입 | 현재 사진의 일관성 근거가 normal 사용을 더 적절하게 정하는가 |
| **N-CORR** | 같은 normal target에 ND형 원래/deflected normal 손실의 적응 결합을 도입 | 일부 감독을 버리는 것보다 제약된 보정 관계로 활용하는 편이 나은가 |

N-AGS/N-NCC는 N0에서 **분기**한다. 연속으로 둘을 누적해야 한다는 설계가 아니다. N-NCC는 원 NeuRIS의 history·normal-difference 조건을 유지하는 이식과 NCC 신호만 공통 gate에 쓰는 통제 비교를 구분한다. 후자는 원방법 재현이 아니라 신호의 효과를 분리하는 비교다.

N-CORR의 공식 normal residual은 L1+cosine이므로 N0의 L1과 비교해 모든 차이를 보정 효과로 돌리지 않는다. 보정 원리 비교에는 **동일 L1+cosine의 비보정 기준**을 사용하거나, 공통 residual로 통일한 이식판임을 명시한다. 보정 변수와 기하 변수의 입력·gradient·자유도·warm-up도 기록한다. 이 후보는 우선 기존 원리의 도입이며 새 방법 기여로 세지 않는다.

DNC는 깊이 감독의 subset을 바꾸므로 normal 감독 선택과 별도로 대비한다. ALS/LoD raycast depth 또는 DA3 depth 중 어디에 적용하는지 먼저 지정하고, 원 sensor depth에 대한 DNC와 다른 관측 가정을 적는다. Prior 깊이 가중·구조 보호는 최초 감독 비교에서 고정하고, 기존 3×2 결과로 필요성이 있는 상호작용만 후속 설계한다.

같은 normal 추정기 출력은 N0와 모든 normal 제어 후보에 제공한다. B0와 N0는 정보 증가의 비교이고, N0와 제어 후보는 정보 사용 원리의 비교다. 어느 normal predictor를 사용할지, 정확한 계수·일정·연산 예산은 실행 전 결박할 항목이며 이번 문서에서 성능을 보고 선택하지 않는다. 기존 결과·도입 후보·아직 수식화되지 않은 새 규칙을 같은 완료 상태로 표기하지 않는다.

## 6. 방법 기여와 박사학위 기여의 현재 위치

- **분석 틀:** 감독 신호·loss로 설계 의도를 읽는 것이 타당하다는 판단이다. 그 분류 자체가 신규성은 아니다.
- **기존 요소 도입:** confidence/consistency weighting, ND형 보정과 원감독 제약, Deb형 연동, 기존 appearance loss는 강한 선행 원리다. 유효하면 채택한다.
- **새 방법 후보:** 독립 기존 기하와 영상 감독의 위치·방향 오류 가정이 다른 조건에서, 어떤 관측 근거가 어느 감독의 영향과 보정 자유도를 허용하는지 연결하는 추정·제약 규칙. 구체식·식별 가정·기존 분리 제어 대비 효과를 제시해야 방법 기여가 된다.
- **설명·검증 기여:** 기존 전체 설계가 충분한 조건과 추가 원리가 필요한 조건, 같은 영역의 수정–손상과 적용 한계를 설명한다. 좋은 결과만 모으거나 평가 항목을 늘리는 것으로 대체하지 않는다.

방법이 아직 확정되지 않았다는 이유로 연구 목적 전체의 차별성을 부정하지 않는다. 동시에 보존·수정의 동시 요구, 새로운 입력 종류, 모듈의 수만으로 방법 신규성을 확정하지 않는다.

## 7. 근거·보존·검증 범위

원문·공식 소스의 명시된 경로를 읽어 설계 의미를 대조했다. 논문 실험을 재현하거나 새로운 방법 효과를 측정한 검증은 아니다. 연구 헌장·DEC-P1-025와 기존 인계는 맥락과 계보로 읽었으며, 이번 사용자 지시를 오래된 ALS/LoD2/명시적 source-decision 필수 설계로 바꾸지 않았다.

이번 문서만 새로 추가한다. 기존 정본·분석·코드·산출물·진행 중 작업·서비스를 보존한다. 프로젝트 도구·테스트·학습·추론·렌더·재구성은 실행하지 않았으며 stage/commit도 하지 않는다. 기본 파일 읽기와 웹 조회·문서 편집만 수행한다.

감사 예외: SPARF의 CVF HTML 재조회가 도구 오류를 반환했다. 이번 결론의 새 근거로 사용하지 않았고 기존 선별 카드의 맥락만 유지한다. 자료 일부는 긴 출력이 절단되어 필요한 절·공식 경로를 좁혀 확인했다.

추가 확인: MonoSDF 프로젝트의 paper 링크는 조회 오류 뒤 arXiv v2 HTML로 복구했다. 공식 HEAD `12513009cd20a08b35ddc2c55a7e42da2c7baf43`는 읽기 전용 원격 조회로 확인했고 loss의 scale/shift 및 normal 경로를 읽었다. NeuRIS의 원문 Table3와 고정 공식 pin의 NCC/history/normal 조건도 다시 읽었다. ND-SDF는 원문 Table6·Appendix B.2와 공식 `system.py`의 normal 회전 및 `loss.py`의 원래/보정 loss를 대조했다. 병렬 검토 두 건은 도구 사용량 제한으로 최종 회신에 실패하여 해당 완료를 검증 근거로 세지 않고, root가 필요한 원문·코드를 직접 확인했다.
