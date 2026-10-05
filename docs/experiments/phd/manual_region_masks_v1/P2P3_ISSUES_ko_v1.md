# P2/P3 수동 영역 작업 이슈

`task_id: PHD-P2P3-MANUAL-REGIONS-v1`, `scientific_verdict: null`

## MR-P2-001 — 차량 가장자리와 지면 마스크 중첩: 해결

첫 P2 `annotation.P2.VB6hd6dQ`의 source 10 RGB 전체 해상도 검토에서,
도로 지면 폴리곤 x457–516/528 일부가 차량 가장자리까지 포함했다.
지면을 x465–488의 좁은 공간으로 줄이고, 차량 차로와 동쪽 통로 차량·수목을
명시적으로 제외했다. `annotation.P2.fur6lKVS`를 새로 생성하고 도면과 배열을 검증했다.
이전 시도/원본은 보존한다. 판단유보 영역은 0이므로 완전한 의미 분류를 주장하지 않는다.

## MR-QA-001 — Chromium 실행 entrypoint 중복: 해결

첫 browser QA 명령에서 기본 entrypoint가 node인 이미지에 `node`를 다시 전달하여
`Cannot find module /qa/node`로 브라우저 시작 전에 종료했다.
실패 attempt의 `failure.txt`를 보존했다. `run_browser_qa.sh`에 `--entrypoint node`를
명시하고 새 `browser_qa.FK8ki4Kw` attempt에서 17개 검사 PASS를 확인했다.
데이터·학습·서비스 변경은 없었다.

## 관측상 한계 — P3 수직뷰 지붕 depth 결손

P3 source 4는 RGB에 지붕이 넓게 보이지만 MVS 결측이 많다. 결측과 경계는 0으로 남기고
경사 source 119의 외벽 관측을 함께 지정했다. native R1 표본은 각각 35,361과 255,178이다.
지붕 복원에 대한 신뢰도 또는 두 source의 정확도 우열로 해석하지 않는다.
