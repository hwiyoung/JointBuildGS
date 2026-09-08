# 다음 세션 인계

2026-09-09 · `PHD-LITERATURE-RQ-v1` · `scientific_verdict: null`

이번에는 지정 목록과 직접 경쟁 추가 문헌을 합쳐 19편을 동일한 1–6 양식으로 분석했다. [목록/규약](README.md), [요소·변수표](01_ELEMENTS_AND_VARIABLES_ko_v1.md), [조건·잔여 오류표](02_CONDITIONS_AND_ERRORS_ko_v1.md), [피드백 비교](03_INFORMATION_FLOW_ko_v1.md), [공백 후보](04_GAPS_AND_RESEARCH_QUESTIONS_ko_v1.md)를 작성했다. 문헌별 확인 수준과 접근 실패는 [출처 감사](05_SOURCE_AUDIT_AND_CONTEXT_ko_v1.md), [이슈](ISSUES_ko_v1.md)에 남겼다.

## 이어갈 핵심

**첫 질문은 기존 처리로도 남는 구체적 복원 손상이 무엇인가이다.** 답을 얻기 전에 GS·교체·명시적 판단·공동/반복이라는 방법 형태를 선택하지 않는다. 시간차는 입력 자체 오차·정합·피복·표현 규모·영상 충분성 중 한 조건이다.

| 우선순위 | 다음에 검토할 질문 | 필요한 reviewable 문서/근거 | 축소·기각 조건 |
|---|---|---|---|
| 1 | G1: 원방법과 강한 기존 조합 이후 실제 무엇이 남는가 | 입력/출력 일치표, 원방법·adaptation 차이, 원인별 failure record | 정합·정제·guided matching으로 충분하면 추가 모듈 후보 철회 |
| 2 | G2: 같은 기하의 구조 보존·세부·외관이 어디서 갈라지는가 | 학습변수/고정증거·density·추출 대비와 평가 대상 | 기존 제어·추출·비GS 경로가 동등하면 새 표현/최적화 후보 철회 |
| 3 | G3: 기존 점수로 최종 손상 위험을 설명할 수 있는가 | uncertainty 대상·공유오차·calibration/ranking/risk–coverage 구분 | 단순 보정이 충분하거나 관측상 비식별이면 방법 복잡화 대신 범위 제한 |
| 4 | G4: 실제 앞단 재추정이 추가 가치를 주는가 | HelixSurf/강한 순차/1회 feedback 대비, 바뀐 정보·비용 | 순차/기존 feedback과 동등하면 단순화 |

다음 문헌 보완은 선택한 질문에 맞춰 좁힌다. G1의 정합 병목이면 기존 robust registration/GNC·sensor error 모델, G2의 세부 병목이면 DN-Splatter·DebSDF·최근 surface methods, G3의 photometric 교란이면 DeSplat/appearance-uncertainty 계열을 우선한다. 이름만 목록에 추가한 후보를 검토 완료로 바꾸지 않는다.

## 놓치면 안 되는 현재 사실

- GeoGS 전문과 실제 로컬 결과가 있다. 옛 문서의 접근/실행 상태를 그대로 재사용하지 않는다. 출판 오류 prior 실험과 프로젝트 ALS adaptation 실험은 다른 근거다.
- GS4Buildings 공식 code는 현재 공개되어 있다. 현재 default와 논문 full arm의 감독 일정은 별도로 확인해야 한다.
- SRDM과 Zhou는 prior 사용/매칭 갱신, HelixSurf는 실제 MVS↔surface feedback을 갖는다. 단계 수로 단방향을 판정하지 않는다.
- Wu 2026은 학습 label 정제/재학습이 있으나 최종 map update에서 앞단을 재호출하는 경로는 미확인이다. ARS도 내부 BA/ACMH 반복과 GS→상류 feedback을 구분한다.
- NeuRIS는 기각 prior를 다시 사용하지 않는 경로다. CL의 dynamic reprojection은 초기 change 증거 전체를 재판정하는 것과 다르다.
- SceneEdited는 직접 경쟁 benchmark이며 주요 복원 비교는 GT change mask를 이용한다. GT-mask 진단을 전체 자동법으로 해석하지 않는다.
- uncertainty ranking·visibility·normal consistency를 현재성 확률이나 절대 기하오차 calibration으로 바꾸지 않는다.

## 향후 비교를 구체화할 때 필요한 결정

정확한 연구 질문 하나와 대상 오류 조건을 먼저 고르고, native 입력 비교와 공통 정보의 adaptation 비교를 나눈다. 어떤 기존 기하/영상·pretrained 정보·camera·참조를 쓰는지, 출력이 point/depth/GS/mesh/texture 중 무엇인지, 무엇을 고정하고 수정하는지, 어떤 기존 조합이 충분한지 판단할 기준을 적는다. 구조의 유효성·현재성·세부 관측 가능성을 label할 독립 근거도 필요하다. 아직 숫자 threshold·새 공식 통과 기준·독립 test membership은 확정하지 않았다.

비교 설계에서 고정 요소를 바꾸는 일과 실제 실행은 별개다. 이 인계는 **새 학습·렌더·방법 실험의 실행 권한을 주지 않는다**. 현재 요청 범위는 문헌 분석과 공백 후보 정리로 끝났다. 향후 실행을 요청받으면 그때 exact target과 정보·출력·자원 범위에 맞춰 구체화한다. 반복·GS를 미리 승인받아야 한다는 뜻이 아니라 이번 문헌 작업을 실행 승인으로 확대하지 않는다는 뜻이다.

## 보존 경계

기존 코드·정본·dirty thesis 문서·untracked 작업·GeoGS/Wu 및 기타 실험 결과·서비스를 유지했다. 새 문서는 `docs/experiments/phd/literature_research_question_v1/`만 소유한다. 원본 논문/임시 PDF 텍스트는 `/tmp` scratch 및 기존 첨부에서 읽었고 이를 영구 원문 보관소로 인증하지 않았다. reference는 평가 전용, E1–E6와 과거 C 계보는 변경하지 않았다. 개발 사례를 독립 confirmatory set으로 승격하거나 scientific verdict를 내리지 않았다.
