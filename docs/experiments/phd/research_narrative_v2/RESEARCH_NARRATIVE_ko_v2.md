# 불확실성 인지형 시기 간 다중소스 3D 융합 기반 Gaussian 재구성 연구 서사 v2

> **지위: WORKING DRAFT — 검토·수정 중. 구현·학습·실험 실행 권한 없음.**
> `scientific_verdict: null`.
>
> 작성: 2026-08-31. 리뷰어: 김휘영.
> 상위 결정: `DEC-P1-025`.
>
> 이 문서는 현재 논의된 연구 배경, 필요성, 공백, 목적과 방법론 원리를 보존하는
> 작업 초안이다. 기존 `research_narrative_v1`, methodology v1, E1–E6 연구계약,
> charter와 decision log를 수정하거나 대체하지 않는다. 방법명, 세부 용어,
> uncertainty estimator, decision unit, loss와 optimization schedule은 후속 검토에서
> 수정할 수 있다.

## 0. 현재 연구 정의

현재 작업명은 **GS 기반 불확실성 인지형 시기 간 다중소스 3D 융합**이며, 영문
후보명은 **Uncertainty-Aware Inter-Epoch Multi-Source 3D Fusion with Gaussian
Splatting (`UIMF-GS`)**이다. 명칭과 약어는 아직 동결하지 않는다.

> 본 연구는 현재 항공영상에서 파생한 3D 기하와 시간적 유효성 및 공간 정합이
> 불확실한 기구축 3D 자료를 선택적으로 결합하여, 현재시점 3D 재구성의 정확도와
> 완전성을 향상하는 불확실성 인지형 시기 간 다중소스 3D 융합 방법을 연구한다.

## 1. 연구 배경

정확하고 최신성이 확보된 도시 3D 정보는 도시계획, 디지털 트윈, 건축물 모델링,
변화 모니터링과 공간분석의 기반이다. 항공영상은 넓은 지역을 반복적으로 관측할 수
있고 취득과 갱신이 용이하다는 점에서 현재시점 도시 3D 정보를 구축하는 주요 자료로
활용된다. SfM과 MVS는 여러 영상에서 대응점과 시차를 추정하여 영상의 외관정보를
3차원 기하로 변환하며, 최근에는 Gaussian Splatting과 미분 가능 렌더링을 이용한
영상 기반 3D 재구성도 발전하고 있다.

영상 기반 3D 재구성의 성능은 영상에서 해당 표면을 안정적으로 관측하고 대응시킬
수 있는지에 의해 결정된다. 충분한 텍스처와 다양한 방향의 관측이 확보된 영역에서는
세밀하고 최신성이 높은 형상을 복원할 수 있다. 무텍스처 표면, 반복무늬, 폐색, 낮은
교차각, 반사, 그림자와 제한된 촬영 범위는 대응점 추정과 깊이 계산의 불확실성을
증가시킨다.

이러한 조건에서 발생하는 오류는 공간적으로 구조화된 형태를 가진다. 특정 지붕면이나
벽면이 누락되거나, 표면이 여러 조각으로 분절되고, 경계와 능선의 위치가 불안정해질
수 있다. 특히 폐색으로 현재 영상에 관측되지 않은 영역은 영상에서 직접 얻을 수 있는
기하정보가 제한된다. 이러한 누락과 불확실성은 최종 점군에 머무르지 않고 표면
재구성, 도시모델 생성, 높이와 체적 측정, 변화탐지와 같은 후속 작업으로 전파된다.

## 2. 연구 필요성

영상 기반 재구성의 공백은 추가 영상 취득, 촬영기하 개선 또는 현재 LiDAR와 같은
새로운 센서의 도입을 통해 줄일 수 있다. 이러한 방법은 현재 상태에 대한 새로운
관측을 제공한다. 동시에 반복적인 재촬영과 센서 취득에는 비행, 장비, 현장 접근,
허가와 데이터 처리에 필요한 비용이 수반된다.

도시에는 과거의 측량과 모델링 사업을 통해 구축된 다양한 3D 공간자산이 존재한다.
ALS 점군은 안정적인 높이와 표면 측정을 제공하고, DSM은 연속적인 표면 높이를
표현하며, LoD 건물모델은 지붕과 벽면의 구조적 관계를 명시적으로 제공한다. 이러한
기구축 3D 자료는 영상의 텍스처와 가시성에 직접 의존하지 않기 때문에 현재 영상에서
불안정하거나 누락된 구조를 보완할 수 있다.

현재 영상과 기구축 3D 자료를 결합하면 각 자료의 상보성을 활용할 수 있다. 현재
영상은 대상의 최신 외관과 변화에 대한 직접적인 관측을 제공하고, 기구축 3D 자료는
영상에서 약하게 관측되는 영역에 안정적인 구조정보를 제공한다. 기구축 자료가 현재
상태와 일치하는 영역에서는 기존 자산을 재사용하여 현재시점 3D 재구성의 정확도와
완전성을 향상할 수 있다.

## 3. 다중소스 3D 데이터 융합과 시기 간 불확실성

본 연구는 현재 영상에서 파생한 3D 기하와 기구축 3D 자료를 결합하여 보다 정확하고
완전한 현재시점 3D 형상을 생성한다는 점에서 **다중소스 3D 데이터 융합**에 속한다.
다중소스 융합은 서로 다른 센서와 표현이 제공하는 상보적인 관측을 정합하고 결합하여
단일 자료보다 높은 정확도, 완전성과 강건성을 확보하는 것을 목적으로 한다.

본 연구가 다루는 자료는 센서와 표현뿐 아니라 취득 시기도 다르다. 현재 영상 유래
형상과 기구축 3D 자료의 차이는 다음 원인의 결합으로 나타날 수 있다.

- 센서와 자료 자체의 `measurement uncertainty`
- 점군·래스터·메시 사이의 공간해상도 및 표현 차이
- 좌표 변환과 정합 과정의 `registration uncertainty`
- 취득 시기 사이에 발생한 실제 `scene change`
- 현재 영상의 가시성 및 기하 관측 한계

기구축 3D 자료는 높은 기하 정밀도를 제공할 수 있으며, 각 구조가 목표시점에도
유효한지는 별도의 `temporal validity`로 표현한다. 현재 영상은 최신 상태를 관측하며,
해당 구조의 정확한 3D 위치와 방향을 추정할 수 있는 정도는 `observability`와
reconstruction uncertainty로 표현한다.

따라서 본 연구의 핵심 문제는 **시간적 유효성과 정합 불확실성이 알려지지 않은
다중소스 3D 자료를 현재시점 재구성에 어디에서, 어떤 방식으로, 어느 정도 사용할
것인가**이다. 이를 위해 measurement uncertainty, registration uncertainty, scene
change와 image observability를 구분 가능한 범위에서 추정하고, 그 결과에 따라 각
소스를 선택하거나 융합하며, 불확실성이 큰 영역을 명시적으로 관리한다.

## 4. 연구 공백

기존 다중소스 3D 융합 연구는 영상과 LiDAR의 정합, 불확실성 기반 가중, 이상치 제거와
점군·표면 결합을 발전시켜 왔다. Prior-guided 3D 재구성은 depth, normal, LiDAR와
도시모델을 재구성의 초기값 또는 기하 제약으로 활용한다. Cross-temporal
reconstruction과 scene update 연구는 과거 장면 표현과 새로운 관측 사이의 변화를
검출하고 현재 장면을 갱신한다.

본 연구는 이러한 연구 흐름 위에서 다음 요소를 하나의 현재시점 재구성 문제 안에서
연결한다.

- 이질적인 기구축 3D 자료의 measurement uncertainty
- 기구축 자료와 현재 영상 사이의 registration uncertainty
- 기구축 형상의 temporal validity
- 현재 영상의 국소적인 3D observability
- uncertainty-aware source selection and fusion
- 선택된 소스에 기반한 실제 geometry refinement와 missing-geometry reconstruction
- 최종 형상의 source provenance와 unresolved uncertainty

핵심 연구 공백은 **시간적 유효성과 공간 정합이 함께 불확실한 다중소스 자료를
현재시점 3D 재구성에 선택적으로 통합하는 방법**이다. 본 연구는 각 불확실성을
구분하여 표현하고, 국소적인 source selection과 fusion을 실제 기하 최적화에 연결하는
방법론과 검증 체계를 연구한다.

## 5. 연구 목적

본 연구의 목적은 현재 영상 유래 기하와 기구축 3D 자료의 불확실성을 추정하고, 각
자료가 제공하는 유효한 정보를 선택적으로 결합하여 현재시점 3D 재구성의 정확도와
완전성을 향상하는 것이다.

구체적인 목표는 다음과 같다.

1. 현재 영상과 기구축 3D 자료 사이의 차이를 설명하는 measurement uncertainty,
   registration uncertainty, temporal validity와 image observability를 체계적으로
   구분한다.
2. 국소 영역과 기하 성분별로 image-derived geometry, prior geometry 또는 두 자료의
   fusion을 선택하는 uncertainty-aware source selection 방법을 설계한다.
3. 선택된 기하정보를 Gaussian 최적화에 반영하여 기존 형상을 refinement하고,
   검증된 3D support가 있는 누락 영역을 실제로 복원한다.
4. 영상 기반 재구성의 정확한 영역을 보존하면서 outdated 또는 misregistered prior에
   의한 geometric contamination을 제어한다.
5. 각 출력 형상에 source provenance, temporal validity와 uncertainty를 연결하여 현재
   형상, 과거 형상 재현과 unresolved region을 구분한다.
6. 직접 기하 정확도와 함께 후속 3D 모델링 및 공간분석으로의 성능 전이를 평가한다.

## 6. 방법론의 원리

본 연구에서는 기구축 3D 자료의 시간적 유효성과 정합 불확실성을 고려하여 현재 영상
유래 기하와 기구축 3D prior를 선택적으로 결합하는 GS 기반 불확실성 인지형 시기 간
다중소스 3D 융합 방법을 설계한다.

### 6.1 출처별 표현과 계보

현재 영상과 그로부터 파생한 SfM/MVS geometry는 현재시점 image-derived evidence를
구성한다. ALS, DSM과 LoD 모델은 각자의 취득 시기, 센서, 해상도와 처리계보를 가진
prior source로 구성한다. 각 소스는 융합 이전까지 분리된 표현과 provenance를
유지한다. 이를 통해 source-specific residual과 uncertainty를 구성하고 최종 형상에
영향을 준 자료의 계보를 추적한다.

### 6.2 Geometric registration

각 기구축 3D 자료는 현재 영상 좌표계에 geometric registration된다. 정합 과정은
신뢰할 수 있는 공통 구조를 이용해 전역 또는 건물 단위 변환을 추정하고, 정합
파라미터와 잔차 분포를 통해 registration uncertainty를 표현한다. 정합 결과는 이후
source selection과 fusion에서 해당 기하 제약의 적용 범위를 결정하는 입력이 된다.

### 6.3 미분 가능 공통 관측공간

현재 형상과 각 prior source는 동일한 현재 카메라에서 depth, normal, silhouette와
visibility로 렌더링된다. 이 source-specific differentiable rendering은 점군,
래스터와 메시처럼 서로 다른 3D 표현을 공통 영상공간에서 비교할 수 있게 한다.
현재 영상의 multi-view consistency, image-derived geometry, prior-rendered geometry와
visibility는 temporal validity, registration consistency와 image observability를
추정하기 위한 관측 근거를 제공한다.

### 6.4 Uncertainty-aware source selection and fusion

방법론은 국소 영역 또는 기하 성분별로 각 소스의 불확실성을 비교한다. 판단 단위는
surface patch, plane segment 또는 spatial cell 가운데 자료 표현과 기하 안정성에
적합한 단위로 설정한다. 각 영역은 다음 reconstruction action과 연결된다.

- `IMAGE`: 현재 영상 유래 기하를 유지하거나 refinement한다.
- `PRIOR`: temporal validity와 registration consistency가 확보된 prior geometry를
  사용한다.
- `FUSION`: 두 소스가 동일한 현재 표면을 상보적으로 지지할 때 결합한다.
- `ABSTENTION`: 현재 형상을 결정할 수 있는 근거가 충분하지 않은 영역을 unresolved
  region으로 기록한다.

Source selection은 이산적인 분류 또는 연속적인 mixture responsibility로 표현할 수
있다. 실제 형식은 calibration, 안정성과 geometry optimization과의 결합 가능성을
기준으로 후속 설계에서 결정한다.

### 6.5 Gaussian 기반 geometry optimization

GS는 현재 형상을 planar Gaussian primitives의 집합으로 표현하고, 현재 영상의
미분 가능 렌더링과 선택된 3D geometry constraint를 하나의 최적화 과정에 연결한다.
현재 형상이 존재하는 영역에서는 uncertainty-aware geometric refinement를 수행한다.
영상 유래 형상이 누락된 영역에서는 temporal validity와 registration consistency가
확보된 prior의 3D support를 이용해 prior-guided primitive initialization 또는
densification을 수행한다. 생성 또는 갱신된 Gaussian은 현재 영상의 visibility와
rendering consistency를 통해 다시 평가한다.

### 6.6 Alternating optimization

현재 Gaussian geometry가 갱신되면 영상과 prior에 대한 렌더링 잔차, visibility와
registration consistency도 함께 변한다. 제안 방법은 다음 두 단계를 반복하는
alternating optimization을 방법 가설로 둔다.

1. 현재 geometry를 기준으로 uncertainty, temporal validity와 source responsibility를
   갱신한다.
2. 갱신된 source responsibility를 기준으로 Gaussian geometry와 primitive set을
   최적화한다.

동일한 registration·change detection·uncertainty 정보를 사용하는 강한 순차적
`register→detect/select→fuse` 방법은 proposed alternating method의 필수 comparator로
유지한다.

## 7. 출력

최종 출력은 현재시점 Gaussian geometry와 함께 다음 정보를 포함한다.

- 각 Gaussian 또는 surface element의 source provenance
- 사용된 prior의 acquisition epoch와 processing lineage
- registration 상태와 uncertainty
- temporal validity
- source selection 또는 fusion responsibility
- geometry refinement 및 primitive generation 이력
- unresolved region과 abstention 상태
- 선택적으로 분리된 historical prior reproduction

이를 통해 현재 관측으로 지지된 형상, 유효한 prior로 복원된 형상, 두 소스가 융합된
형상과 현재 상태를 확정할 수 없는 영역을 구분한다.

## 8. 연구질문

- **RQ1:** 현재 영상 유래 기하와 기구축 3D 자료의 measurement uncertainty,
  registration uncertainty, temporal validity와 image observability는 어떤 관측을
  통해 구분하고 추정할 수 있는가?
- **RQ2:** 이러한 불확실성을 이용한 국소 source selection and fusion은 fixed-source
  및 fixed-weight fusion보다 낮은 현재시점 기하오류를 달성하는가?
- **RQ3:** Prior-guided Gaussian refinement와 primitive generation은 영상 기반
  재구성의 성공영역을 보존하면서 누락영역의 정확도와 완전성을 향상하는가?
- **RQ4:** Source selection과 geometry를 반복 추정하는 alternating optimization은
  강한 순차적 registration–change detection–fusion 방법보다 어느 조건에서 추가적인
  이득을 제공하는가?
- **RQ5:** 직접 기하 개선과 geometric contamination 억제는 서로 다른 후속 3D
  모델링 및 공간분석에서도 일관된 성능 향상으로 이어지는가?

## 9. 박사학위 기여 구조

1. **시기 간 다중소스 3D 융합의 불확실성 모형**

   Measurement uncertainty, registration uncertainty, temporal validity와 image
   observability를 분리하고, 각 요소가 source selection과 geometry reconstruction에
   미치는 관계를 정립한다.
2. **불확실성 인지형 Gaussian 재구성 방법론**

   Source-specific differentiable rendering, uncertainty-aware source selection and
   fusion, Gaussian geometric refinement와 prior-guided primitive generation을
   결합하여 유효한 기구축 자료를 현재 형상으로 전환한다.
3. **선택적 융합의 검증 방법론**

   Image-only, prior-only, registered-prior-only, simple fusion, fixed/adaptive
   weighting과 강한 순차 fusion을 비교하고, geometry accuracy, completeness,
   calibration, risk–coverage, non-degradation 및 contamination을 함께 평가한다.

## 10. 현재 미동결 항목

다음 항목은 현재 서사의 의미를 구현하기 위한 설계 대상이며 이 문서로 동결하지
않는다.

1. 정식 방법명과 약어
2. `multi-epoch`, `inter-epoch`, `temporal validity`의 최종 한글 표기
3. source 종류와 지원 가능한 기하 자유도의 범위
4. measurement uncertainty, registration uncertainty와 temporal validity의 관측량
5. decision unit: surface patch, plane segment, spatial cell
6. source selection: discrete action, mixture responsibility 또는 hybrid
7. fusion operator와 geometric refinement 방식
8. prior-guided primitive initialization/densification의 허용 조건
9. alternating optimization과 강한 순차 comparator의 공정한 계산 계약
10. 최종 downstream probe와 independent-scene 검증 범위

## 11. 정본 및 관련 문서와의 관계

- 상위 승인 문제정의: `docs/research/06_DECISION_LOG.md`의 `DEC-P1-025`
- 현행 연구계약: `docs/research/00_RESEARCH_CHARTER.md`~`06_DECISION_LOG.md`
- 기존 박사 서사 정본: `docs/experiments/phd/research_narrative_v1/`
- 기존 최소위험 방법 설계: `docs/experiments/phd/methodology_v1/`
- 상세 semantic method 작업 초안: `docs/experiments/phd/methodology_v2/`
- prior 주입 문헌 검토: `docs/experiments/phd/prior_injection_survey_v1/`

이 작업 초안은 위 문서들을 소급 수정하지 않으며, 사용자 검토와 별도 승인 전에는
새로운 실행 조건, loss, threshold, 실험 또는 scientific claim의 근거가 아니다.
