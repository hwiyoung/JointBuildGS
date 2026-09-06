# A — 실행·설계 이슈

> 2026-09-06. 기존 입력·산출물은 보존. `scientific_verdict: null`.

| ID | 문제 → 원인/범위 → 조치 → 해결 상태 |
|---|---|
| A-001 | `DISCRETE_RANGE`가 `P2_X066_Y043` IMAGE를 조건부 채택했으나 UAS 점군 기준 미달. 관측가림·공유오차·유한 격자·표면모형·datum 중 원인은 분리하지 못함. strict 행동은 ABSTAIN으로 유지하고 동일 단위/곡선/오차를 기록했으며 유리한 문턱으로 수정하지 않음. **판단 정확성 미해결** |
| A-002 | A-v1 `source_input_state`가 raw MVS부재와 존재하지만 eligible planar patch가 없는 상태를 모두 `NO_ELIGIBLE_PLANAR_PATCH`로 표시. 후보 목록·점·결정은 올바르게 absent였으나 상태 설명이 불충분. 원본을 수정하지 않고 `A-FIGURES-v2/source_availability_annotations.json`에 `ABSENT / PRESENT_NO_ELIGIBLE_PLANAR_PATCH / AVAILABLE`와 raw count 보충. **추적성 보완 완료, 원본 상태필드는 이 보충표와 함께 읽음** |
| A-003 | 부모 하나만 이동한 FUSION의 compatibility에 정확한 이동후 점쌍거리 대신 삼각부등식 상한 `d0+|ΔP−ΔM|`을 적용. 거짓 허용은 막지만 실제 가까워진 부모도 추가 유보할 수 있음. v1 프로토콜 구현과 결과 보존, 이 근사의 영향은 후속 독립 ablation 대상. **보수성 한계 유지** |
| A-004 | Gaussian+uniform 비교는 원논문 확률센서의 bounded 변형으로서 full published MVS·registration·calibration 시스템은 재현하지 않음. 원출력·식·수정점·adapter를 설계와 결과에 공개. **강한 전체 기존법과의 성능 비교는 부분 완료** |
| A-005 | EPSG:32632 UAS와 EPSG:25832 프로젝트의 datum/epoch/수직 정확도 관계 미보정. A 입력에는 UAS가 없고 C의 평가를 legacy numeric-frame 진단으로 제한. 현재 참오차·과학적 판정은 확정하지 않음. **보정 미완료** |
| A-006 | postprocessing table을 터미널에 요약하려던 일회성 `python -c`의 f-string escaping이 SyntaxError로 종료. 원측정·평가·그림에 영향 없고 필요 표는 JSON을 직접 읽는 checked-in `a_figures.py`로 생성. **복구 완료** |
| A-007 | 그림 v1 육안검사에서 사례 수치 label이 축 위쪽에 붙고, risk-null 설정별 개수가 차트 밖 JSON에만 있음. v1을 보존하고 v2에 공통 오차축·짧은 제목·label 간격·null 개수를 반영. **그림 QA 완료; 값 불변** |
| A-008 | 개발 strict API의 미검증 사유 이름을 검증계약 key에도 재사용하면 향후 호출자가 `not_calibrated=true` 같은 부정형 flag를 승인으로 오독할 수 있음. 실제 A-v1은 검증계약을 전달하지 않아 전수 ABSTAIN이었고 이 분기는 실행되지 않음. 현재 source에서는 긍정형 `CERTIFICATION_CONTRACTS`로 분리하고 부정형 flag 전부True도 승인하지 않는 검사 추가. 원 snapshot/실측 결과 보존, 조건부/strict 실측 행동 불변. **API 잠재 오용 보완, 총14검사 PASS** |

원점 native row 해시·정확 좌표 검산과 실행전 Docker13검사·현재 source14검사는 모두 통과했다. 검산 통과는 관측모형·현재 사용 정확성의 검증을 대신하지 않는다.
