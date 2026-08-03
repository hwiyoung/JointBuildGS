# C1/C2 대표 3동 정성·정량 비교판 v1 기술 보고서

## 결론

v1은 첫 표본 `DEBY_LOD2_4907177`의 C1 input principal section에서 독립 UAS roof
reference가 단면 band를 통과하지 않아 fail-closed로 중단됐다. C1/C2 계산 실패가 아니라
고정 단면 위치 선택 실패다.

- 기술 상태: `BLOCKED_SECTION_REFERENCE_NOT_VISIBLE`
- partial: 15 files, 1,705,454 bytes
- 생성 범위: raw 4 PNG, C1 input 4 PNG, projection receipt 7개
- partial 처리: 삭제·덮어쓰기·재사용하지 않고 보존
- Roofer/G2/GS/metric 재실행: 0
- scientific_verdict: null

## 원인과 recovery

기존 단면은 building bbox 중앙을 지나도록 고정됐다. 작은 표본에서 roof reference가 bbox
중앙 band 밖에 있어 `projected_visible_count=0`이었다. recovery는 outcome이나 metric을
보지 않고 roof reference XY median을 지나는 동일 주축 단면을 사용한다. 모든 method와
input/output에 같은 단면 anchor를 적용하고 새 namespace에서 한 번만 렌더링한다.
