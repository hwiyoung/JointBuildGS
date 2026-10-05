# R1–R5 백그라운드 실행 병렬화

- 시각: 2026-09-18 11:21 KST 전환.
- 요청: 같은 실험의 진행 속도를 높이고, 작은 영역에서도 시간이 오래 걸리는 원인 확인.
- 범위: 기존 ALS-adapted GeoGS 개발 실험. `scientific_verdict: null`.
- 실행: `jbgs-r1r5-parallel-20260918T022117Z.service`.
- artifact: 현재 attempt의 `parallel_20260918T022117Z/`.

## 원인

RTX 3090 24 GiB 두 장 중 GPU 1에서만 조건을 순차 실행했다. 관측 시 GPU 1은
96–98% 사용 중이었고 GPU 0은 학습 작업 없이 비어 있었다. 각 조건은 같은
Anchor 8,000에서 30,000까지 22,000회 학습한다. 공간 ROI를 작게 잡아도
RGB loss는 1,400×1,013 전체 영상에서 계산하므로, ROI 면적에 비례해서
계산량이 줄어들지 않는다. 학습 과정에서 가우시안은 백만 개 이상이다.
또한 native clone/split 임계값의 scene extent는 카메라 중심의 분포에서
계산하므로 ROI 면적만으로 primitive 수를 예상할 수 없다.

기존 완료 기록의 실제 소요:

| 단계 | 소요 시간 |
|---|---:|
| R2–R5 MVS 학습 | 조건당 약 64–72분 |
| R1 DA3 학습 | 약 94분 |
| R2–R5 MVS TSDF 추출 | 조건당 약 3–8분 |
| R1 DA3 TSDF 추출 | 약 15분 |

R2 DA3 OOM 두 번에 각각 약 21분, 19분이 소요되었다. 해당 조건은 보류하며
이번 변경으로 다시 실행하지 않는다. 현 시점 완료는 6/15, 실행 대상은 8조건,
별도 실패·보류는 R2 DA3 1조건이다.

## 조치

1. GPU 1의 실행 중인 R3 DA3 Docker 컨테이너를 새 실행 관리자가 인계한다.
   기존 Python 큐 프로세스만 SIGSTOP하고, 학습 컨테이너와 Docker CLI는
   계속 실행한다. 체크포인트를 다시 불러오거나 학습을 재시작하지 않는다.
2. GPU 0은 R1 `local_prior0` 사전 검증부터 시작한다. 나머지 독립 조건은
   하나의 큐에서 중복 없이 분배한다. GPU 하나에 GPU 단계 하나만 배정한다.
3. 기존 R3 학습 컨테이너가 종료된 뒤 receipt를 수집하고, 그때 기존 큐
   프로세스를 종료하여 이후 조건의 중복 실행을 막는다. 이때 기존 systemd
   unit의 signal 종료는 계획된 소유권 인계이며 새로운 학습 실패가 아니다.
4. RAM 예약량은 합계 64 GiB로 제한한다. 학습은 각각 32 GiB 두 개까지,
   TSDF 추출은 56 GiB 한 개만 실행한다. 추출이 대기하면 이후 학습보다
   먼저 자원을 받는다. 기존 실제 MemAvailable/GPU 여유 검사도 유지한다.
5. 두 작업의 상태와 기존 실패를 `execution/status.json`에 단일 writer가
   기록한다. 기존 뷰어 게시기가 이 파일과 원래 출력 경로를 계속 읽는다.

학습 영상, Anchor, seed, 반복 수, 해상도, 모든 loss, 국소 mask, native 보호,
densification, TSDF 설정은 유지한다. 기존 recovery의 cudaMallocAsync 설정을
두 worker에 동일하게 유지한다. 동일 모델 GPU로 작업을 분산하며 결과의
bitwise 동일성을 별도로 주장하지 않는다. 실패한 조건은 자동 재시도하지 않는다.

## 검증과 추정의 범위

- Docker 단위 검사 4개 PASS: 두 학습/단일 추출 RAM 제약, FIFO 추출 우선권,
  실행 중 컨테이너의 완료 후에만 기존 큐 종료, 실패한 학습의 추출 금지.
- 기존과 신규 snapshot의 `run_queue.py`, `phase.py`, `train_observed.py`,
  `intervention.py`, `prepare_da3.py` byte 동일 확인.
- `handoff.json`에 기존 컨테이너 ID와 학습 재시작 없음 기록.
- 11:25 KST: GPU 0 R1 사전검증 8,100회 PASS 후 `local_prior0` 본 단계 시작.
  인계 당시 12,140회였던 GPU 1 R3는 13,480회 이상으로 진행하고 finite=true를
  유지했다. `runtime_verification.json`에 상태·GPU·commit·검증 receipt를 기록했고
  HTTP 뷰어의 두 worker 상태 반영도 확인했다.
- 현재 실행 상태는 `parallel_20260918T022117Z/status.json`, 인계 후 원래 큐
  종료 증거는 완료 시 생성될 `retirement.json`으로 구분한다.

정상 진행하는 8조건은 기존 단일 GPU 예상 11–14시간에서 약 6–8시간으로
줄어들 것으로 추정한다. 11:30 기준 약 17:30–19:30 KST이며, 두 GPU가
계속 사용 가능하고 추가 실패가 없다는 조건부 예상이다. RAM 때문에 표면
추출은 직렬화되므로 정확히 2배 빨라진다고 주장하지 않는다. R2 DA3의
성공적 완료 시각은 이 추정에 포함되지 않는다.

독립 systemd 서비스이므로 대화 종료 후에도 진행한다. 완료한 결과는 뷰어에
자동 반영된다. 자동 채팅 알림이나 상시 agent polling은 설정하지 않았다.
