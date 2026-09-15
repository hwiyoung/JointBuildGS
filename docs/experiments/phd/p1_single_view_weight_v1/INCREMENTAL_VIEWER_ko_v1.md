# 가중치별 완료 즉시 비교 뷰어

- 사용자 지시: “학습 완료되는 순서대로 뷰어에 차례차례 최종 결과 먼저 처리해서 보여줘.”
- 주소: [가중치 0·1·4 비교](http://127.0.0.1:8910/app/p1_weights.html)
- 상태: `WAITING_INDIVIDUAL_FINALS` — 2026-09-15 21:34 KST 확인.
- `scientific_verdict: null`

## 처리 순서

각 조건의 **30,000회 학습 완료 receipt**가 PASS이면 그 조건부터 처리한다.
둘 이상 완료돼 있으면 receipt의 시작 시각+소요 시간으로 완료 순서를 정한다.
완전 상태 checkpoint·최종 PLY·마스크·설정의 해시를 확인하고, 별도 출력 경로에서
원래 native renderer로 raw/post TSDF512와 RGB/depth를 생성한다.
검증된 raw RGB 표면과 0100_D·0099_D 렌더가 준비되면 해당 조건만 manifest에 등록한다.
나머지 조건은 대기이며, 이전 실험이나 중간 checkpoint로 채우지 않는다.

GPU0을 기존 학습과 같은 파일 잠금으로 사용한다. GPU0 학습이 끝나면 개별 표면을
처리하며, GPU1은 기존 큐의 alpha4 학습과 후처리가 계속 사용한다.
현재 실행의 학습·마스크·기존 후처리 스크립트는 변경하지 않았다.
따라서 기존 세 조건 공동 정량 후처리도 예정대로 수행한다. 조기 표시용 추출은
그와 경로를 분리한 추가 산출물이며, 동일 설정의 native 추출을 반복할 수 있다.
뷰어 등록은 정량 평가 완료나 과학적 판정을 의미하지 않는다.

## 비교 화면

- 가중치 0·1·4의 세 화면에 회전·이동·확대를 동기화한다.
- 원래 30m P1 평가 범위와 주변 80m 표시 범위를 선택한다. 감독 마스크와 구분한다.
- 0100_D 학습뷰와 0099_D 비교뷰에서 원사진·실제 RGB·camera-Z depth를 비교한다.
- depth 색상 범위는 모든 조건에 고정된 50–85m다. 표시용 범위이며 학습값을 변경하지 않는다.
- 브라우저는 60초마다 manifest를 다시 읽는다. 다른 조건을 기다리지 않고 준비된 결과를 표시한다.
- 완료된 개별 결과의 `publication.json`은 덮어쓰지 않는다. 표시 manifest만 원자적으로 갱신한다.

## 실행과 검증

- 시작 스크립트: `scripts/phd/p1_single_view_weight_v1/start_incremental_viewer.sh`
- 감독 서비스: `jbgs-p1-weight-incremental-viewer.service`
- 서버: 기존 `jbgs-geogs-rgb-viewer-8910` 유지.
- 외부 payload 루트 기준:
  `phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/viewer_rgb_v1/p1_weights_v1/`
- `source/`: 실행 스크립트·설정·native finalizer·파서·표시 exporter·앱 snapshot와 해시.
- `alpha_N/extraction/`: 해당 최종 checkpoint의 조기 표시용 추출과 receipt.
- `alpha_N/publication.json`: 해당 조건의 실제 표시 기하·RGB·depth와 학습 계보.
- `worker_status.txt`, `worker.log`, `builder_status.json`, `publication_events.log`: 진행 및 실패 증거.
- `training_unchanged.sha256`: 기존 학습과 후처리·마스크 불변성 검사.

Docker CPU 검사 5개 PASS: 완료 순서, 한 조건만 완료됐을 때의 즉시 등록,
이전 등록 결과 보존, 잘못된 완료 상태/조건/마스크 거절, 추출 설정과 표면 해시 불일치 거절.
이는 작은 fixture의 처리 검증이며 실제 새 학습 결과가 아니다.

실제 Docker Chromium 검사 50개 PASS:
두 표시 범위와 두 촬영 뷰, 세 조건의 대기 상태, 카메라 동기화,
원사진 로드, 390px 화면, 기존 matched 페이지 유지, 브라우저·네트워크 오류 0개.
증거: `browser_qa.mHWcfTEb/receipt.json`과 desktop/mobile PNG.
현재 새 결과 표면의 실물 확인은 학습 완료 후에 가능하다.

## 예상 시간 — 2026-09-15 21:34 KST 관측

alpha0/1은 각각 추가 학습 14,510/14,270회(목표 22,000회) 부근이며 약 20분 남았다.
최근 속도와 alpha4의 전체 추가 학습을 합치면, **alpha4까지 학습 완료는 22:45–23:05 KST**로
추정한다. 저장·처리 속도 변화에 따라 달라질 수 있다.
같은 P1 native 추출의 이전 실행 소요는 약 161초였으며, 각 조건의 뷰어 표시는
해당 학습 완료 후 표면 추출·CPU 표시 변환에 추가로 몇 분이 필요하다.
모든 조건의 정량 후처리 종료 시각과 개별 뷰어 등록 시각은 구분한다.
