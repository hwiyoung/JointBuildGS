# 0100_D 수동 분류 영역 가중치 — 실행 기록

- task_id: `PHD-P1-SINGLE-VIEW-WEIGHT-v1`
- revision: `annotated_support_v2`
- scientific_verdict: null
- 상태: CPU 22개 검사 및 GPU 3개 기술 점검 PASS, alpha0/1 본 학습 시작
- 실행: `attempt.annotated.uOkHWmgi`
- supervisor: `jbgs-p1-weight-annotated-uokhwmgi.service`

## 현재 설정

0100_D의 수동 R1(113,103픽셀)은 alpha0/1/4로 비교한다. 수동 R2/R3은 1로,
R4/미분류/범위 밖/결측은 0으로 둔다. 사용 영역은 571,461픽셀이다.
RGB 판독으로 assistant가 다각형을 지정했고, R1 후보에는 prior–MVS 비교도 사용했다.
자동 segmentation이나 calibrated confidence를 사용한 결과가 아니다.

다른 97개 depth와 RGB 98장, prior 0.005 및 native 보호를 고정한다.
모든 조건의 전체 MVS 계수는 0.05다. 원래 유효 depth 픽셀 수로 손실을 평균하므로
alpha에 따라 분모가 변하지 않는다. alpha1은 이 사용 영역에서의 새 대조군이다.

## 확인한 기술 증거

- 세 조건 모두 같은 완전 상태 Anchor8k 복원 검사 PASS.
- 세 조건의 8001회 첫 렌더와 raw MVS loss, 200회 카메라 순서가 일치한다.
- 각 조건에서 0100_D가 실제 두 번 선택됐고 첫 선택은 iteration 8041이다.
- 첫 target depth 손실의 alpha1 기준값/기울기, alpha0 R1 기울기 0,
  alpha4 R1 기울기 4배, R2/R3 기울기 동일성, 제외 영역 기울기 0을 확인했다.
- 위 검사는 감독 구현의 적용 증거다. 전체 형상 개선이나 일반화의 증거가 아니다.

## 실행과 결과 위치

외부 정본은 `../JointBuildGS-artifacts/phase-payloads/phd/p1_single_view_weight_v1/`
`PHD-P1-SINGLE-VIEW-WEIGHT-v1/attempt.annotated.uOkHWmgi`다.

- `status.txt`: 현재 큐 상태
- `gate.json`: 실제 세 조건 기술 점검
- `train/alpha_0`, `train/alpha_1`, `train/alpha_4`: 조건별 로그와 완료 receipt
- `postprocess/`: 완료된 세 학습의 native TSDF512 추출, 0100/0099 RGB-depth 비교,
  R1/기타 사용 영역/제외 영역 입력 적합도와 동일 참조점 UAS 개발 평가
- `REPORT.md`: 후처리 완료 시 생성하는 보고서

큐는 alpha0/1을 GPU0/1에서 병렬 실행한 다음 alpha4와 후처리를 수행한다.
목표는 각 조건 iteration 8000에서 30000까지다. report/최종 receipt의 존재와 PASS를
확인하기 전에는 완료로 보고하지 않는다. background 실행은 자동 채팅 재호출을 뜻하지 않는다.

## 조건별 완료 즉시 뷰어 등록

사용자의 후속 지시에 따라 [개별 완료 결과 뷰어](INCREMENTAL_VIEWER_ko_v1.md)를 추가했다.
각 조건의 30k 학습이 끝나면 GPU0에서 별도 표시용 native 추출을 수행하고,
그 조건의 최종 표면과 0100_D·0099_D RGB/depth부터 등록한다. GPU1의 alpha4 학습은
기존 큐가 계속 수행한다. 세 조건이 모두 끝날 때까지 표시를 보류하지 않는다.
기존 학습·공동 정량 후처리 큐의 스크립트와 설정은 그대로 유지한다.

## 보존한 이전 시도

`attempt.UB7vkBLu`는 밖의 유효 depth를 1로 유지하던 초기 조건이다. 사용자의 범위 정정으로
본 학습 alpha0/1의 마지막 기록 8888/8889에서 중단했고 관련 source, mask, log, preflight
checkpoint와 `interruption_receipt.json`을 보존했다. 현재 비교 결과에 완료 조건으로 포함하지 않는다.
