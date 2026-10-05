# P2/P3 영역 가중치 0·1·4 — 실행 계약

`task_id: PHD-P2P3-REGION-WEIGHT-v1`  
`scientific_verdict: null`  
승인: 2026-09-15 사용자가 P2/P3 수동 영역 초안을 확인하고 학습 및 뷰어 연결을 요청했다.

## 비교 질문과 고정 조건

각 대상에서 **동일한 수동 영역 마스크의 R1 가중치만** 0·1·4로 바꾸면,
현재 MVS를 향한 보정과 주변 표면 유지가 어떻게 반응하는지 확인한다.

| 항목 | 고정 조건 |
|---|---|
| 대상과 조건 수 | P2/P3 각각 α=0/1/4, 총 6회 |
| 초기 상태 | 대상별 동일한 complete Anchor8k |
| 본 학습 | 8,001–30,000, 조건마다 Anchor에서 새로 시작 |
| RGB·카메라 순서 | P2 57장, P3 137장, 기존 train membership와 RNG 유지 |
| depth 범위 | 방금 생성하고 검증한 모든 train-view 마스크 |
| 영역 배율 | R1 α, R2/R3 1, R4/R5/R6·invalid 0 |
| MVS 계수 | 고정 0.05, adaptive controller 비활성 변경을 receipt에 명시 |
| Prior 계수·보호 | 0.005, native 보호 유지 |
| 기하 정규화 | 기존 native 항 유지, PGSR 추가 없음 |
| loss 분모 | 해당 뷰의 원래 유효 depth 표본 수; α나 사용 영역 합으로 재정규화하지 않음 |
| 사전 실행 | 각 α 8,001–8,300; 전체 카메라 실제 적용과 같은 첫 렌더·순서 확인 |
| 출력 | 30k checkpoint, native RGB/depth, 동일 raw TSDF512, viewer용 기하 |

**P1과의 차이:** P1은 0100_D 한 카메라의 수동 범위만 제한하고 다른 97개 depth는 유지했다.
P2/P3는 이번에 승인한 전체뷰 마스크를 모든 해당 train 카메라에 적용한다.
그러므로 α 비교는 대상 내 통제 비교이며 P1/P2/P3의 마스크 정책이 같다는 주장을 하지 않는다.
α=0도 RGB·prior 감독이 남으므로 해당 건물 형상 고정이나 prior-only 결과가 아니다.

## 마스크와 입력 계보

수동 폴리곤은 [P2/P3 영역도 보고서](../manual_region_masks_v1/P2P3_REGIONS_ko_v1.md)를 따른다.
prior–MVS 잔차 임계값으로 만든 자동 신뢰도 마스크가 아니다.
R1은 시험 대상이며 깊이 정확성·실제 변화·Gaussian 제거를 판정하지 않는다.

- P2: `annotation.P2.fur6lKVS`; 수동 source 10/4, 전체 57뷰.
- P3: `annotation.P3.5CQlJP1P`; 수동 source 119/4, 전체 137뷰.
- native/RGB 정렬과 입력 SHA를 검증한 `rgb_masks.npz`를 카메라마다 복사하여 고정했다.
- 모델용 `mask/manifest.json`에 전체 카메라 stem, 배열 SHA, R1/사용 표본 수를 기록했다.
- 원본 RGB, MVS, prior, 기존 학습 결과는 변경하지 않았다.
- 학습·사전 실행·표면 추출에는 평가 reference를 마운트하지 않는다.

## 실제 연산 검증

새 source snapshot은 원래 MVS source에서 `train.py`, `jbgs_state.py`만 바꾸고
`jbgs_region_weight.py`, 기존 검증된 수식 helper `jbgs_weight_core.py`를 추가했다.
complete anchor의 optimizer·보호·카메라 스택·RNG 복원 검사를 유지한다.

검사는 다음 경계를 구분한다.

1. CPU 기하/연산 회귀: 27개 PASS, 1개 외부 source fixture 검사 skip.
   skip된 parent source 경계는 실제 bundle preparation의 전체 parent SHA 검사와
   GPU complete anchor 복원 검사가 별도로 확인한다.
2. 실제 첫 유효 prediction에서 detached depth-loss algebra: α=0의 R1 gradient 0,
   α=4의 R1 gradient 4배, R2/R3 gradient 유지, 제외 gradient 0.
   이는 depth 항 미분 검증이며 Gaussian 최종 이동량 또는 최종 복원 효과의 증명이 아니다.
3. 300-step 사전 실행: 모든 카메라의 실제 마스크 적용, native 유효 표본 분모,
   실제 loss와 R1/other/excluded 기여의 합을 검증한다.
4. 세 조건의 첫 prediction SHA와 카메라 추출 순서가 동일해야 gate를 통과한다.
5. 조건별 full-state 파일 SHA와 30k 완료 receipt를 확인한 뒤에만 후처리한다.

샘플링/RNG는 바꾸지 않는다. 카메라는 매 step 기록하고 지역 기여는 각 카메라 첫 방문과
100-step 간격으로 기록한다. GPU에는 현재 카메라 마스크만 보내 불필요한 상주 메모리를 줄인다.

## 실행 및 완료 순서

독립 systemd user service 두 개가 소유한다. 채팅 tool session 종료에 종속되지 않는다.
프로세스 하나는 GPU0의 P2, 다른 하나는 GPU1의 P3를 순차 처리한다.
기존 P1 학습·후처리·조건별 뷰어 등록을 보존한다.

- P2 사전 실행은 비어 있는 GPU0에서 시작할 수 있다.
- P3 사전 실행과 P2 본 학습은 P1 최종 등록 및 기존 후처리 완료 후 시작한다.
- 각 대상은 사전 실행 0→1→4, gate, 본 학습 0→표면 추출·뷰어 등록→1→등록→4→등록 순서다.
- 한 조건의 결과를 표시하기 위해 다른 조건들의 완료를 기다리지 않는다.
- GPU lock은 기존 P1과 공유하며 점유 GPU나 기존 프로세스를 강제 종료하지 않는다.
- 실패 시 해당 대상 상태와 로그에 남기고 중단한다. 실패 결과를 성공이나 대조군으로 대체하지 않는다.

## 뷰어

`http://127.0.0.1:8910/app/p2p3_weights.html`

P2/P3 각각 기존 평가 범위와 주변 포함 범위를 선택한다. 같은 3D 카메라로 세 α를 비교하고,
수동 기준 영상 두 장의 실제 RGB·GS RGB·GS depth를 선택한다. 두 영상 모두 학습뷰이며
독립 평가뷰라고 부르지 않는다. P2 depth 표시 50–85m, P3 10–125m를 각 조건 간 고정했다.
기하 raw TSDF512 추출값은 대상별 기존 camera-radius 기반 값으로 고정하고 후처리에서 검사한다.

뷰어 검증: 서로 다른 두 train 카메라의 RGB/depth가 뒤섞이지 않는지, 하나씩 등록되는지,
이전 등록 결과가 보존되는지를 CPU fixture 2개에서 확인했다. 실제 Docker Chromium에서는
4개 표시 범위·2개 기준 사진·3개 조건 상태·카메라 동기화·390px 화면·기존 비교 페이지를
포함한 96개 검사 PASS. 현재 초기 검사는 대기 상태의 표시 검증이다.
실제 최종 결과는 각 학습·추출 완료 receipt와 해당 publication으로 확인한다.

## 완료 기준과 해석

대상별 `status.txt = PASS_ALL_THREE_TRAINED_AND_PUBLISHED`와 각 α의
training receipt `PASS`, extraction receipt `PASS`, `publication.json`이 모두 있어야
그 대상의 세 조건이 완료된 것이다. 전체 viewer manifest의 등록 수는 6/6이어야 한다.

이 실행 범위는 마스크 반응과 실제 최종 표면·렌더의 개발 비교다.
입력 MVS 적합도나 학습 RGB 일치도를 독립 기하 정확도로 해석하지 않는다.
새 UAS/LoD2 정량 평가, 자동 confidence 추정, prior 영역 가중치 변경은 이 실행에 포함하지 않는다.

## 경로

외부 bundle:
`../JointBuildGS-artifacts/phase-payloads/phd/region_weight_v1/PHD-P2P3-REGION-WEIGHT-v1/attempt.wwxHlpSc`

- `preparation.json`, `frozen_files.sha256`: 입력·source·명령 고정
- `P2/`, `P3/`: config, mask, preflight, gate, train, status, supervisor log, systemd unit
- `browser_qa.94CZMidM/receipt.json`: 초기 실제 브라우저 검사
- viewer payload: 기존 `geogs_mvs_pgsr_v1/.../viewer_rgb_v1/p2p3_weights_v1`
- viewer `P2/alpha_N`, `P3/alpha_N`: 개별 extraction/display/publication

source/scripts/config를 완료 뒤 바꾸어 동일 attempt를 재해석하지 않는다.
고친 실행은 새 attempt와 새 receipt를 만든다.
