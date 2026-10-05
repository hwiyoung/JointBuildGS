# v4 실행 이슈

2026-09-07 · `scientific_verdict: null`

| ID | 상태 | 문제와 원인 | 조치·범위 |
|---|---|---|---|
| WV4-001 | CONTROL_ADDED | P1 기본 master838의 native 지원이 매우 작음. FOV 포함과 관측 지원은 다르며 실제 전경 가림·깊이 무효를 확인. | 기본 결과 보존. 전체113뷰의 영상 자체 XY 지원 최대 시점90으로 별도 실행. 같은 규칙의 P2 전체66뷰 대조도 추가. 레퍼런스 기반 시점 선택 없음. |
| WV4-002 | RECOVERED_AND_VERIFIED | 추가 평가 Python은 완료됐지만 실행 중 root가 launcher에 comparison 분기를 추가하여 바깥 bash가 EOF/exit2 반환. | 현재와 snapshot driver 해시·현재 bash -n PASS·Python COMPLETE·양지역 후보/input/output 해시 검증을 wrapper_completion_exception.json에 보존. 수치 재실행·원출력 덮어쓰기 없음. 진행 중 launcher 편집을 중단함. |
| WV4-003 | ADDITIVE_METADATA_CORRECTION | 추가 시점 support-audit의 자유 설명이 초기 ‘40뷰’를 상속했지만 실제 실행은113/66뷰 전부. | 실제 loop·view count·원receipt 해시는 유지. 각 외부 run의 scope_text_correction.json에 설명 정정. 수치·선택·후보 변경 없음. |
| WV4-004 | OPEN_REPRODUCTION_LIMIT | 원저자 코드/PSMNet/다중시점 전방교차/실측ALS궤적과 차이. 원문 면적·집계 문턱 미공개. | 모든 대체와 설정·민감도를 기록. 입력 지원 부족을 분리. 원저자 전체 성능·실패로 확대하지 않음. |
| WV4-005 | OPEN_REFERENCE_LIMIT | UAS header32632/working25832, datum/epoch·정합 차이 미보정, 변화 point GT 부재. | 동일 고정 참조의 양방향 편차·결손 진단만 수행. 현재성·오류 정답·공식 품질 verdict 생성 없음. |
| WV4-006 | DISPLAY_CORRECTED_R2 | 첫 WebGL 4패널의 색 공간 변환으로 높이색이 HTML 범례·단면보다 옅게 표시됨. | 첫 viewer/QA 보존, RGB를 선형 색 공간으로 전달한 r2 추가. 점군·정량은 불변. 최종 실제 픽셀-범례 일치 검증 추가. |
