# 학위 연구 질문에 따른 문헌 분석 v1

2026-09-09 · `PHD-LITERATURE-RQ-v1` · 문헌 분석/공백 후보 · `scientific_verdict: null`

연구 질문은 **오차와 표현 수준이 다른 기존 3D 기하와 현재 영상으로, 유효한 구조의 손상을 통제하면서 결손·오류를 보완하고 현재 기하·관측 가능한 세부·외관을 복원할 수 있는가**이다. GS, 소스 교체, 명시적 판단 모듈, 공동·반복 최적화는 검토할 수단이다. 시간차는 정합·피복·표현 규모·입력 오류·관측 부족과 함께 다루는 조건이다.

이번 정리에서 가장 먼저 좁혀진 것은 신규성 주장이다. prior 기각, 품질에 따른 보존·갱신, 구조와 세부의 조절, 감독 재가중, 앞단 기하 재추정을 포함한 반복은 이미 연구되어 있다. **추가 방법이 필요한 조건과, 기존 해결책을 적용한 뒤에도 최종 복원에 남는 손상**이 연구 공백 후보의 중심이다. 이는 문헌 부재나 신규성의 확정 판정이 아니다.

## 읽는 순서와 산출물

| 문서 | 제공 내용 |
|---|---|
| [요소·변수 비교](01_ELEMENTS_AND_VARIABLES_ko_v1.md) | 각 논문의 일곱 요소, 실제 추정·고정 변수, 제약 해제의 영향 |
| [조건·잔여 오류 비교](02_CONDITIONS_AND_ERRORS_ko_v1.md) | 가정/실제 검증 조건/실패 상태/최종 출력 영향 |
| [정보 흐름과 피드백](03_INFORMATION_FLOW_ko_v1.md) | 가까운 방법들의 갱신 경로, 반복에서 새로 생기는 정보와 재사용 정보 |
| [선행 해결·공백 후보](04_GAPS_AND_RESEARCH_QUESTIONS_ko_v1.md) | 가까운 대안과 단순 조합, 최소 비교, 기각 조건 및 우선 질문 |
| [출처·현재 맥락](05_SOURCE_AUDIT_AND_CONTEXT_ko_v1.md) | 원문/공식 구현 버전, 검색 범위, 기존 GeoGS/Wu 결과의 정확한 지위 |
| [다음 세션 인계](06_NEXT_SESSION_HANDOFF_ko_v1.md) | 우선 확인할 주장, 비교 설계의 미결정 사항, 작업 경계 |
| [접근·검토 이슈](ISSUES_ko_v1.md) | 접근 실패·판본 차이·남은 미확인 및 검증 결과 |

## 논문별 근거 카드

모든 카드는 `1 문제와 입출력 → 2 기여의 위치 → 3 고정과 수정 → 4 실제 검증 → 5 잔여 오류 → 6 공백 후보`를 따른다. 서지/버전과 절·페이지·표·그림·코드 위치를 카드 안에 연결한다. 번호가 다른 HTML/PDF를 구분하며, 확보하지 못한 locator는 미확인으로 남긴다.

| 문헌 | 비교에서의 역할 |
|---|---|
| [SRDM](cards/srdm.md) | LiDAR로 영상 매칭을 개선하고 부적합 prior를 기각하는 가까운 기하 복원 |
| [Zhou 2020](cards/zhou_2020.md) | 기존 ALS+항공영상의 guided matching·변화 갱신 |
| [Wu et al. 2023](cards/wu_2023.md) | 시계열 sensor mesh의 가시성·품질 선택과 접합 |
| [Wu–Vallet 2026](cards/wu_vallet_2026.md) | 기존 LiDAR+새 항공영상의 갱신 점군 |
| [Qin 2014](cards/qin_2014.md) | 무색 기존 모델의 영상 변화 검정; 탐지 구성요소 |
| [3DGS](cards/3dgs.md) | 영상 장면 표현·밀도 제어·렌더링 기준 |
| [2DGS](cards/2dgs.md) | 영상 기반 표면 표현·기하 감독·추출 기준 |
| [GS4Buildings](cards/gs4buildings.md) | LoD2 구조 prior와 항공영상 복원 |
| [GeoGS](cards/geogs.md) | 구조 anchor/protection와 영상 깊이·외관 refinement |
| [ARSGaussian](cards/arsgaussian.md) | 항공 RGB+LiDAR의 정합·감독·GS 복원 |
| [AGS-Mesh](cards/ags_mesh.md) | sensor depth/mono normal 감독 선택 및 추출 |
| [SpotLessSplats](cards/spotlesssplats.md) | transient 억제·감독/장면 교대 갱신·삭제 위험 |
| [CL-Splats](cards/cl_splats.md) | 기존 색상 GS+국소 새 영상의 변화·보존·갱신 |
| [GaussianUpdate](cards/gaussianupdate.md) | 기존 GS의 외관·기하 변화 분리와 갱신 |
| [NeuRIS](cards/neuris.md) | 현재 표면의 사진 검정으로 prior 감독을 기각 |
| [BayesRays](cards/bayesrays.md) | 학습된 radiance field의 공간 불확실성; 진단 구성요소 |
| [VCR-GauS](cards/vcr_gaus.md) | adaptive normal 감독·위치 gradient·분할 |
| [HelixSurf](cards/helixsurf.md) | MVS와 implicit surface를 서로 갱신하는 강한 피드백 대안 |
| [SceneEdited](cards/sceneedited_2026.md) | 기존 3D+영상 변화 검정/지도 갱신 benchmark 경쟁 |

목록은 닫혀 있지 않다. 시작 목록 외 문헌은 주장의 직접 경쟁성에 따라 추가했다. 검색되었지만 전문 검토하지 않은 후보는 [출처 감사](05_SOURCE_AUDIT_AND_CONTEXT_ko_v1.md)에 별도로 남긴다. 카드에 없는 문헌의 기능 부재를 추정하지 않는다.

## 판독 규약

- **원문 사실**: 원문/공식 코드에서 읽은 절차·수치·관찰. **저자 해석**: 원인을 설명하거나 일반화하는 저자의 논증. **우리 추론**: 그 사실을 학위 조건에 연결한 가설/비교 설계. **미확인**: 접근/명세/검증으로 확정하지 못한 사항.
- **관측된 실패/악화**: 특정 조건과 지표에서 확인된 현상. **미평가**: 확인한 평가가 해당 질문을 측정하지 않음. **범위 밖**: 원방법의 입력/목표와 다른 문제. **미확인**: 평가 여부/결과를 결정할 근거 부족. 이 네 상태를 서로 바꾸지 않는다.
- 요소표의 **새/기존 사용/미확인**은 논문 내부 기여 위치를 분해한 것이며 최초성·우월성 점수가 아니다. 한 논문을 여러 요소에 배정한다.
- 직접 비교는 **목표별**이다. 점군 갱신은 기하 비교에서 직접적일 수 있지만, NVS/텍스처 mesh 전체 비교에는 공통 후단 또는 native 출력별 평가가 필요하다. 같은 입력을 지원하지 않으면 adaptation과 정보·비용 차이를 드러낸다.
- 최적화 내부 피드백, 감독 선택 갱신, 앞단 입력 재추정, 새 관측 추가를 구별한다. 단계가 있다고 단방향으로 분류하지 않고, 반복한다고 독립 증거가 늘었다고 보지 않는다.

## 보존과 연구계약

지정된 기존 문서는 맥락/검색 색인으로 읽었으며 정본·dirty 문서·구현·기존 결과를 수정하지 않았다. 이번 사용자 목적을 이 문헌 분석의 상위 범위로 적용하고, 옛 설계의 특정 판단 모듈·표현을 필요조건으로 재도입하지 않았다. E1–E6와 C 계보·GT separation은 그대로다. 새 학습·렌더·재구성·방법 실험은 시작하지 않았다. `scientific_verdict: null`이며 commit/stage/push를 하지 않았다.
