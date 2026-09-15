# P2/P3 가중치 실험 백그라운드 착수

2026-09-15 22:52 KST 관측. `scientific_verdict: null`.

두 독립 systemd user service가 실행 중이며, 학습 도구 세션 종료에 종속되지 않는다.
입력/source/마스크/스크립트는 immutable bundle `attempt.wwxHlpSc`에 고정했다.

| 대상 | 현재 확인된 단계 | 이후 자동 순서 |
|---|---|---|
| P2 | α0/1/4의 300-step GPU preflight와 matched gate PASS | P1 후처리 완료 → α0 본 학습·등록 → α1 → α4 |
| P3 | P1 후처리 및 최종 뷰어 등록 완료 대기 | α0/1/4 preflight·gate → α0 본 학습·등록 → α1 → α4 |

P2 사전 실행에서 조건마다 57개 카메라를 전부 확인했다. 같은 첫 prediction SHA와
카메라 순서가 일치했다. 이는 사전 검사 완료이며 30k 본 학습 완료나 복원 성능 결과가 아니다.
P3 사전 실행은 아직 완료됐다고 보고하지 않는다.

P1은 α4까지 학습이 완료됐고 22:51:56 KST에 세 조건의 뷰어 등록도 모두 완료됐다.
기존 정량 후처리는 아직 진행 중이다.
새 작업이 P1의 마지막 결과 표시를 밀어내지 않도록 의존 순서를 고정했다.

## 뷰어와 상태

- URL: `http://127.0.0.1:8910/app/p2p3_weights.html`
- P2 unit: `jbgs-p2-region-weights-attempt.wwxhlpsc.service`
- P3 unit: `jbgs-p3-region-weights-attempt.wwxhlpsc.service`
- 실행 bundle: `../JointBuildGS-artifacts/phase-payloads/phd/region_weight_v1/PHD-P2P3-REGION-WEIGHT-v1/attempt.wwxHlpSc`
- 각 대상의 `status.txt`, `supervisor.log`, `train-alphaN.driver.log`, `train/alpha_N/receipt.json`을 함께 본다.
- viewer `P2/alpha_N/publication.json`, `P3/alpha_N/publication.json`이 개별 최종 표시 완료 증거다.
- 각 조건은 학습 완료 → 표면 추출 → RGB/depth 확인 → 개별 등록까지 끝난 후 다음 α를 시작한다.
- browser QA `browser_qa.94CZMidM`: 96개 PASS. 대기 상태·원사진·카메라 동기화 표시를 확인했으며
  아직 존재하지 않는 최종 결과로 대체 표시하지 않았다.

## 시간 추정

기존 같은 기반 MVS/0.005/native의 22k continuation 실측은 P2 약 71.6분,
P3 약 56.8분이다. 새 영역 마스크·고정 MVS 계수에서는 속도와 Gaussian 수가 달라질 수 있다.
P1 의존 작업과 사전 실행, 조건별 표면 추출을 포함하면 첫 결과 등록은
**9월 16일 00:00–00:30 KST**, 6조건 등록 완료는 **02:00–03:00 KST**를 현재 추정 범위로 둔다.
이는 예약 완료 시각이 아니며 실제 첫 본 학습 속도로 갱신해야 한다.

## 검증

- CPU loss/카메라/lineage suite: 27 PASS, 외부 source fixture 1 skip; actual parent hash audit와 P2 GPU restore 별도 PASS.
- 두 train-view 렌더 순서 및 개별 등록 fixture: 2 PASS.
- 실제 브라우저: 96 PASS.
- bundle frozen-file SHA 및 기존 P1 training-unchanged SHA 재검사 PASS.
- GPU 작업은 기존 lock을 공유하며 최대 GPU별 1개다. 기존 프로세스·서비스·입력·결과를 중단하거나 덮어쓰지 않았다.

최신 상태는 위 runtime 파일이 정본이며 이 문서의 시각별 관측은 자동 갱신되지 않는다.
