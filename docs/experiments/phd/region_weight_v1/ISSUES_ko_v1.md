# 영역 가중치 진단 이슈

## 2026-09-16 — prior .0005 P1 후처리 설정 경로 누락: 복구 진행

- 문제: 뷰어 P1 추가 조건은 실패, P3는 QUEUED였다. P2는 학습·추출·등록 PASS.
- 확인된 원인: P1 publisher는 `/driver/viewer_config.json`을 읽는데 공통 worker가
  `/viewer_config.json`만 마운트했다. P1은 30k 학습 PASS(3,053.50초) 후
  추출 staging 시작에서 FileNotFoundError로 중단됐다. GPU0 worker가 종료되어
  그 뒤의 P3는 시작하지 않았다. 학습 수렴·GPU 메모리 오류가 아니다.
- 첫 복구의 nested read-only mount도 실패했다(exit 125). `/driver`가 읽기 전용이고
  그 안에 mount 대상 파일이 없어 Docker가 만들 수 없었다. 해당 시도와 로그를 보존했다.
- 조치: 별도 recovery driver 복사본에서 P1 설정 lookup을 `/viewer_config.json`으로
  통일했다. 이후 bundle 생성기에도 동일 수정을 반영했다. 동결된 원래 소스는 보존하고,
  P1의 완료 checkpoint로 후처리만 재시작했다. 재학습하지 않는다.
- P3는 원래 동결 worker를 사용해 비어 있는 GPU1에서 별도 실행을 시작했다.
  P2의 완료 결과와 원래 오류 로그·종료 상태 기록을 보존했다.
- 첫 recovery: `attempt.rNaCh1sO/recovery.f4k4rzVZ` (mount 실패).
- 현재 recovery: `prior_weight_followup_v1/PHD-P1P2P3-PRIOR0005-R1A4-v1/attempt.rNaCh1sO/recovery.z7tZrFVz`.
- 실패 로그: `P1/display_stage.log`; 원래 상태 복사본: recovery의 `*.initial_status.txt`.
- 복구 관측: P1은 staging 통과 후 실제 GPU 추출 중, P3는 preflight PASS 후 본 학습 중.
  P2는 게시 완료. 완료 판정은 각 status/receipt 및 현재 recovery의 completion_check로 확인한다.

## 2026-09-16 — P3 평균 잔차의 과도한 해석: 정정

- 문제: 0142_D R1 MAE 약 3.2m를 광범위한 지붕 미보정처럼 설명했다.
- 원인: 평균에 치우친 설명에서 작은 잔차의 대다수와 수십 m 잔차의 소수를 구분하지 않았다.
- 조치: 분포·위치·표시 범위를 추가 집계하고 기존 진단 문서의 해당 해석을 정정했다.
  α=4 중앙값 2.323cm, 10m 초과 7.203%가 절대잔차 합 92.345%를 차지한다.
- 상태: 설명과 시각화 정정 완료. 입력의 실제 오류 원인은 미확정; 학습 입력 변경 없음.
- 근거: `weight_response_v1/response.json`, `FOLLOWUP_PLAN_20260916_ko.md`.

## 2026-09-16 — 추가 도면 사전 검토: 수정

- 최초 그림의 colorbar와 CDF 축 제목이 겹쳤고, P3 사선뷰 예시의 무효 prior 값
  Infinity가 JSON에 직렬화되어 표준 JSON 파싱에 실패했다.
- 무효 prior를 null로 기록하고 `allow_nan=False`로 직렬화 검증을 강화했다.
  범례 간격을 늘리고 제목을 줄였다. 원본 학습·입력·수치 집계는 변경하지 않았다.
- 최초 결과는 `weight_response_v1_preflight_20260916`에 보존했다.

## 2026-09-16 — 추가 뷰어 이미지 전환: 수정·검증 완료

- 최초 CPU 브라우저 검사에서 이미지 decode 오류가 발생했다. 표시 이미지의
  완료 여부만 기다리던 검사와 동일 img 요소의 비동기 교체를 함께 보완했다.
- 새 이미지의 decode를 마친 후 표시 요소를 바꾸고, 검사도 해당 선택의
  데이터·SHA·표시 완료 상태를 기다린다. 오래된 선택의 완료는 무시한다.
- 최초 실패 receipt는 `weight_response_v1/browser_qa_first/receipt.json`에 보존했다.
  최종 `browser_qa/receipt.json`은 5개 촬영 영상, 수치·예시·SHA 연결,
  P3 정정 설명, 기존 뷰어 링크, 모바일 및 브라우저 오류 등 18개 검사를 통과했다.
