# 대표 3동 정성·정량 비교판 v3 기술 보고서

## 결론

v3는 첫 표본의 raw image 지붕 투영 4개를 만든 뒤 C3 source binding 검증에서
fail-closed로 중단됐다. C1/C2 패널 생성 전에 멈췄으므로 C1/C2 결과 실패가 아니다.

- 기술 상태: `BLOCKED_C3_TERMINAL_SOURCE_BINDING_INCOMPLETE`
- v3 partial: 8 files, 1,472,858 bytes
- 생성 범위: `DEBY_LOD2_4907177` raw image projection 4 PNG와 receipt 4개
- partial 처리: 삭제·덮어쓰기·재사용하지 않고 보존
- Roofer/G2/GS/metric 재실행: 0
- large archive hash pass: 0
- scientific_verdict: null

## 원인

v3 preflight는 표본 3동의 C1/C2/C3 operation unit ID와 terminal 존재를 확인했다.
그러나 renderer의 `load_geometry`는 모든 terminal에 `input`과 `r_derived` bytes/SHA
레코드가 있다고 가정한다. 재사용 C1/C2 terminal은 이 레코드를 가지지만 U_target
census에서 새로 실행된 C3 terminal schema는 output record만 가진다. 파일은 존재하지만
승인된 source record 없이 ad-hoc으로 해시를 만들어 연결하지 않고 중단한 것이 맞다.

## 다음 경계

사용자가 요청한 순서대로 C1/C2-only 비교판을 먼저 완성한다. 이 successor는 C1/C2의
완전한 terminal source binding만 사전검사하고 C3–C5를 읽거나 표시하지 않는다. C3는
그 뒤 별도 task에서 source-run의 input/r_derived identity를 additive manifest로 봉인한
후 동일 comparison matrix에 연결한다.
