# 대표 3동 정성·정량 비교판 v2 기술 보고서

## 결론

v2는 3D label 회귀를 통과했지만 두 번째 표본 `DEBY_LOD2_4907176`에 봉인된 C3
operation unit이 없음을 fail-closed로 발견해 완료하지 않았다.

- 기술 상태: `BLOCKED_SAMPLE_C3_SOURCE_UNAVAILABLE`
- v2 partial: 121 files, 101,650,984 bytes
- partial 처리: 삭제·덮어쓰기·재사용하지 않고 보존
- Roofer/G2/GS/metric 재실행: 0
- source payload 재해시: 0 — v1 closed attestation 재사용
- scientific_verdict: null

## 원인과 재실행 방지

기존 표본 조건은 strict independent UAS reference만 확인했고 세 방법의 봉인된 operation
unit 가용성을 사전 조건으로 넣지 않았다. 수정본은 출력 namespace를 만들기 전에 세 표본의
C1/C2/C3 operation unit이 모두 존재하는지 전수 검사해야 한다. outcome metric이나 gate는
선정에 사용하지 않는다.
