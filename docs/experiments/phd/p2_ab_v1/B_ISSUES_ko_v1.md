# B 개발 실행 issue log

2026-09-06. `scientific_verdict: null`.

| ID | 문제와 확인 원인 | 조치·해결 상태 | 보존 결과 |
|---|---|---|---|
| B-001 | PRIOR-v1은 선택된 source bbox로 crop해서 A간 고정 영상범위 비교에 부적절 | COMMON 전체 native P2 prism에서 모든 방법에 같은 crop를 정의. PRIOR-v2와 RANGE/SCORE/BAYES/IMAGE-v1 주비교 | PRIOR-v1 smoke 산출 보존, 결과 선택/튜닝에 사용하지 않음 |
| B-002 | RANGE의 72 geometry proposal 모두 존재 mask 경계 검사 거부 | 실행 실패가 아니라 현재 제약의 결과. fixed GS와 같아 추가 재구성 이득 없음. 경계 검사 완화로 결과를 사후 변경하지 않음 | RANGE-v1 history와 final 동일 geometry 보존 |
| B-003 | DN 이미지에는 `python` executable이 없고 `python3` 사용 | 버전 점검을 `python3`로 수행: torch2.2.2+cu118/gsplat1.0.0. 프로젝트 호스트 실행 없음 | 실제 ns-train과 무관한 read-only preflight 오류 |
| B-004 | DN-v1 official SH degree0 경로가 colors `[N,1,3]`를 gsplat non-SH API에 넘겨 첫 forward assertion | 원코드 수정 없이 official default SH degree3로 DN-v2 새 실행. SH0-only B와 representation/appearance 자유도 차이를 명시 | DN-v1 config/adapter/training.console.log와 실패 산출 보존 |
| B-005 | DN finalizer의 PNG byte identity 검사가 PIL/OpenCV 인코딩 차이로 실패. decoded RGB 오차는 0 | native evaluation과 partial alias 보존. 새 `dn_splatter_original_v2` adapter에 같은 decoded pixels를 확인 후 B canonical target bytes copy. 11뷰 exact byte identity receipt | 학습·렌더 재실행이나 결과 선택 없음 |

DN-v1 실패는 `training.console.log`의 `dn_model.py:495 → gsplat/rendering.py:202`
`AssertionError: torch.Size([2427, 1, 3])`로 확인했다. 실패한 실행을 성공·성능 결과로 세지 않는다.

DN-v2는 96 step(마지막 checkpoint 95), 초기·최종 별도 11뷰 렌더와 camera matrix
일치 검증을 완료했다. `result.json`과 `handoff_identity_receipt.json`,
`finalization_receipt.json`에서 source handoff와 공통 target을 추적한다.
