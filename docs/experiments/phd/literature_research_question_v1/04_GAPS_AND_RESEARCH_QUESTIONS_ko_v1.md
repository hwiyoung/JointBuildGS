# 선행 해결 범위와 검증할 공백 후보

2026-09-09 · `scientific_verdict: null` · 아래의 후보/비교/기각 조건은 우리 연구 설계 추론이다.

학위의 대상은 서로 다른 기하와 영상에서 상보적 정보를 얻어 복원 품질을 개선하는 것이다. 기존 기술이 충분한지부터 검증한다. 모든 조건을 하나의 새 알고리즘으로 처리해야 한다는 전제도 두지 않는다. 문헌은 일부 문제를 이미 해결했고, 서로 다른 가정에서 유효하다. 조건의 차이와 검증 부족은 그 자체로 방법론적 결함이 아니다.

## 신규성 근거에서 제외해야 할 주장

| 제안하려는 기능/주장 | 가까운 선행 해결·직접 근거 | 이번 판정 |
|---|---|---|
| LiDAR/기존 3D로 영상 결손·오류 보완 | [SRDM §3–4](cards/srdm.md), [Zhou §3–4](cards/zhou_2020.md), [ARSGaussian §3](cards/arsgaussian.md) | 목표/기능 자체는 이미 존재 |
| 불일치 prior를 검정·기각 | SRDM two-step+truncation, Zhou change 후 재매칭, [Qin roof 검정](cards/qin_2014.md) | 기각 또는 source 교체라는 이름은 신규성이 아님 |
| 품질/시기/관측 범위에 따라 유지·갱신 | [Wu 2023](cards/wu_2023.md), [Wu 2026](cards/wu_vallet_2026.md) | 단순 최신 우선 방법만을 약한 상대법으로 삼을 수 없음 |
| 큰 구조 보존+영상 세부·외관 | [GS4Buildings](cards/gs4buildings.md), [GeoGS](cards/geogs.md) | 가장 직접 겹치는 목적과 제어 |
| 오류·불완전 prior와 pose perturbation 강건성 | GeoGS Table7, ARSGaussian Tables5–9 | “기존 방법은 오류 prior를 평가하지 않았다” 기각 |
| supervisor confidence/기각 갱신 | [AGS-Mesh](cards/ags_mesh.md), [NeuRIS](cards/neuris.md), [VCR-GauS](cards/vcr_gaus.md) | 반복 감독 선택 자체는 이미 존재 |
| 판단과 reconstruction의 공동·교대 최적화 | [SpotLessSplats §4](cards/spotlesssplats.md), [GaussianUpdate §3](cards/gaussianupdate.md) | 별도 단계 또는 교대 형식만으로 차별화 불가 |
| 후단 표면으로 앞단 depth를 다시 계산 | [HelixSurf](cards/helixsurf.md) | 실제 upstream feedback도 이미 존재 |
| 과거 영역 보존·현시점 GS 갱신·외관 변화 분리 | [CL-Splats](cards/cl_splats.md), GaussianUpdate | 기존 색상 GS라는 입력 차이는 adaptation 문제, 능력 부재 아님 |
| spatial uncertainty·risk 기반 cleanup | [BayesRays](cards/bayesrays.md), SpotLessSplats UBP | 불확실성 존재만으로 새로움 아님; 추정대상/실패 조건 검토 필요 |
| old cloud+images 변화/갱신 benchmark | [SceneEdited](cards/sceneedited_2026.md) | 평가축·데이터 조합 자체의 최초 주장 기각; GT mask 조건·합성/실제 차이를 확인 |

## 공백 후보 G1 — 두 입력이 모두 틀릴 수 있을 때 남는 복원 오류

**질문:** 기존 robust registration, guided matching, denoise·visibility·quality selection을 적용해도, 한 지역 안에서 서로 다른 오류를 가진 기하들이 유효 구조 손상과 결손/오류 복원의 상충을 남기는가?

**출발 근거:** Zhou는 변화 후 재매칭의 실패를, Wu 2026은 image mesh에 따른 잘못된 변화 검출을 보고한다. ARS는 LiDAR noise/정제/결손이 최종 렌더에 영향을 줌을 평가한다. 이들은 각각의 조건에서 관측한 사실이다. 같은 문제의 모든 원인이나 최신 강한 조합의 실패를 입증한 것은 아니다.

**종류:** 가장 먼저는 적용 조건/검증 부족 후보다. 충분한 증거가 있어도 기존 cost·constraint가 오배제/오수정을 강제하고, 그 규칙만 고쳤을 때 개선된다면 방법론적 후보가 된다. “한쪽 오류가 많음”만으로 explicit source-decision 모듈을 필요조건으로 두지 않는다.

**가장 가까운 대안:** SRDM/Zhou의 원 guided matching, Wu의 quality/visibility 선택, ARS의 전처리·정합·depth generator, robust confidence loss. 이들이 만든 기하에 공통 mesh+texture 또는 GeoGS를 연결한 조합도 전체 상대법이다. 논문 부품을 엮었다고 새로운 독립 논문 방법인 것처럼 이름 붙이지 않는다.

**최소 비교:** image-only, prior-only, registered prior, union, fixed/confidence weighting을 기본 진단으로 두고, 입력에 적용 가능한 가장 가까운 원방법 및 강한 조합 하나 이상과 제안 변경을 비교한다. 원입력에서 시작하는 전체 비교와 동일 중간 기하에서 사용하는 규칙만 바꾸는 비교를 분리한다. prior 유효/오류, image 양호/오류, 둘 다 부적합한 조건과 양호한 조건을 함께 포함한다. 시기 변화는 오류의 한 하위 원인으로 둔다.

**기각/축소:** 단순 정합·정제·guided matching/후처리로 문제가 해소되면 추가 방법 후보를 기각한다. 평가 전용 local selection oracle도 고정 소스보다 이득이 없으면 local arbitration 주장을 축소한다. 이 oracle은 주어진 후보들의 선택 진단이지 모든 연속 복원의 이론적 상한이 아니다. 충분한 후보가 없으면 선택 알고리즘보다 후보 생성/관측 조건이 문제일 수 있다.

## 공백 후보 G2 — 유효한 구조의 보존과 관측 세부·외관 개선의 동시 성립

**질문:** 입력에 이미 있는 좋은 구조를 덜 손상시키면서 영상이 실제로 지지하는 위치·곡률·경계·작은 형상과 외관을 개선할 수 있는가? 기존 구조 보호/정제/추출을 맞춰도 추가 설계가 필요한가?

**출발 근거:** GS4Buildings의 세부 평활화, GeoGS의 평균 성공과 지역 악화, 2DGS의 regularization trade-off, AGS-Mesh의 추출 민감도가 확인된다. 프로젝트의 현재 GeoGS ALS 변형도 일부 렌더 개선과 표면 완전성 저하를 동시에 기록하지만, 이는 native 원방법의 실패 증거가 아니다([맥락](05_SOURCE_AUDIT_AND_CONTEXT_ko_v1.md)).

**종류:** 검증 부족과 방법론적 한계 후보의 혼합이다. 표현 규모 차이는 예상되는 입력 조건이며 오류로 자동 분류하지 않는다. 외관에 나타나는 선명함이 실제 3D 세부인지를 확인해야 한다.

**가장 가까운 대안:** GeoGS 원 protection/controller, GS4Buildings, AGS-Mesh/VCR-GauS의 geometry supervision, 원 depth를 사용하는 TSDF·IsoOctree·기존 mesh refinement+texture. GS 없는 경로도 동등한 출력 목표로 비교한다.

**최소 비교:** 동일한 source support/기하에서 원 제어, 합리적인 고정 국소 제어, 기존 adaptive 제어를 비교한다. 위치/방향/scale 제약과 density 변경을 분리하고, 같은 학습 결과의 추출/후처리 변경을 별도로 대조한다. 전체 정확도·완전성·현재성·renderer 외관 외에 사전 지정한 경계/곡면/세부의 복원과 이미 좋은 부위의 악화를 기록한다. 좋은 외관을 같은 renderer로 평가했는지, 추출 mesh texture를 평가했는지도 구분한다.

**기각/축소:** 기존 고정 제어나 추출 변경이 동등하면 새 reconstruction 설계를 기각한다. 작은 구조의 개선이 참조 sampling·추출 해상도·더 많은 관측·더 긴 계산에 의해 설명되면 해당 원인으로 귀속한다. 영상으로 식별되지 않는 세부를 복원했다고 주장하지 않는다. 필요한 제품 품질을 비GS가 충족하면 GS 필요성을 주장하지 않는다.

## 공백 후보 G3 — 불확실성이 실제 수정 위험을 설명하는 범위

**질문:** residual, normal consistency, visibility, feature mask, spatial uncertainty가 최종 기하의 예상 손상을 얼마나 설명하는가? 두 입력의 공유 오류와 판단 불가를 다룰 때 기존 점수를 보정하는 것으로 충분한가?

**출발 근거:** BayesRays는 일부 inconsistent-view artifact를 낮은 uncertainty로 평가하는 실패를 보고한다. SpotLessSplats는 드문 유효 관측의 pruning 손실을 명시한다. NeuRIS/AGS/VCR는 모델 기반 감독 조절을 실제로 제공한다. 따라서 confidence를 만든다는 기능보다 그 의미·의존성·결과와의 관계가 비교 대상이다.

**종류:** 우선 검증/보정 후보다. 방향 일치와 위치오차, epistemic uncertainty와 실제 변화, 관측 부재와 자료 오류는 다른 대상이다. 명시적 확률을 출력하지 않는 방법을 calibration하지 않았다는 이유만으로 방법 실패로 분류하지 않는다.

**최소 비교:** 기존 score의 원형, 같은 score의 단순 calibration, visibility/관측수 기준, 추가 evidence를 사용하는 변경을 같은 복원기에서 비교한다. 독립 참조에서 error ranking과 calibration을 구분하고 같은 coverage에서의 구조 손상, 같은 risk에서의 coverage를 본다. abstention/no-update를 포함하되 그것만 늘려 오류를 낮추는 결과를 품질 개선으로 주장하지 않는다. 같은 영상에서 만든 MVS·normal·feature·검정 residual의 의존성을 유지/분리하는 비교를 둔다.

**기각/축소:** 단순 calibration/가시성 처리로 충분하면 새 uncertainty 모델을 기각한다. 허용된 evidence로 차이를 식별할 수 없다면 재관측 또는 확인 범위 제한의 문제로 축소한다. 새 관측이 이득을 만들었다면 그 관측을 기존 방법에도 제공한 뒤 비교한다.

## 공백 후보 G4 — 반복이 추가로 회복하는 정보와 비용

**질문:** 동일한 원관측을 쓰더라도 현재 표면으로 가시성·대응·깊이·pose를 재추정해야만 회복되는 오류가 남는가? 한 번의 강한 순차 처리나 기존 HelixSurf형 feedback보다 더 필요한 것은 무엇인가?

**출발 근거:** 기존 연구에 반복/앞단 재추정이 있으므로 “단방향의 한계를 joint로 해결”은 출발 논증이 될 수 없다. GeoGS의 weight controller, NeuRIS의 일방적 prior 기각, HelixSurf의 MVS 재계산처럼 무엇을 재방문할 수 있는지 비교한다.

**종류:** 앞선 G1/G2에서 구체적인 실패가 남은 뒤에만 검토할 방법론적 후보. 시간차가 없어도 관측/정합/표현 오류로 발생할 수 있다.

**최소 비교:** 같은 evidence와 변수 자유도에서 강한 순차 1회, 동일 판단 재사용, supervisor 갱신, 실제 앞단 재추정, 제안 반복을 비교한다. 같은 연산량과 실용 예산 두 관점으로 비교하며 warm-start와 from-scratch를 구분한다. 반복 중 어느 정보가 언제 바뀌어 어떤 수정이 가능해졌는지 기록한다.

**기각/축소:** 순차법이나 기존 feedback이 같거나 낫다면 더 단순한 방법을 채택한다. 반복이 초기 조건 차이·추가 계산·추출 차이만 반영하면 반복의 방법 기여를 기각한다. 새로운 증거 없는 재채택이 손상을 늘리면 no-update를 포함한 안정적인 경로로 축소한다.

## 우선 연구 질문과 판단 순서

1. **RQ-A:** 가장 가까운 기존 처리와 강한 조합 뒤에도, 유효 구조 손상과 보완 실패가 함께 남는가? 먼저 원인/적용조건을 구체화한다(G1).
2. **RQ-B:** 같은 지원 기하에서 최종 표면·관측 세부·외관의 개선이 동시에 전달되는가? 초기화·감독·density·추출의 기여를 나눈다(G2).
3. **RQ-C:** 기존 evidence로 수정의 위험을 설명할 수 있는가? 단순 보정과 비교하고 식별 불가를 분리한다(G3).
4. **RQ-D:** 위에서 남은 오류에 실제 앞단 재추정/반복이 추가 가치를 주는가? 유용한 실패 기전이 확인된 뒤 검토한다(G4).

이는 학위의 확정 방법이나 새 실험 순서를 승인한 것이 아니다. 가장 가까운 방법의 성공을 보존하고, 개선과 악화의 전체 범위를 평가한 다음 기여를 결정한다. 기존 개발 P1/P2/P3·199동을 독립 확증 집합으로 바꾸지 않으며 참조 geometry와 temporal label은 방법 입력으로 누출하지 않는다.
