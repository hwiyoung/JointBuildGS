# P2 W2C U_target 199 contract results recovery R1 v1

## Metadata

- handoff_id: `P2-W2C-UTARGET199-CONTRACT-RESULTS-RECOVERY-R1-v1`
- task_id: `P2-UTARGET199-CONTRACT-RESULTS-RECOVERY-R1-v1`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `93a2d03783403826d21b33bf6c554fc8ff3e2600`
- explicit_user_authorization: `APPROVED_IN_SESSION_TO_CONTINUE_UTARGET199_EXECUTION`
- predecessor: `P2-W2C-UTARGET199-CONTRACT-RESULTS-v1/300-closed.json`
- scientific_verdict: `null`

## 목적과 범위

선행 실행은 과학 입력을 열기 전에 accepted-receipt validator의 artifact-root 인자 누락으로
종료됐다. 이 recovery는 validator에 artifact root를 읽기 전용으로 전달한 뒤, 이미 승인된
`U_target=199 × C1/C2/C3` 계약을 변경 없이 한 번 실행한다.

- 199동 모두 유지; 72동이나 10동으로 사전 제외하지 않는다.
- 목표 산출물은 597개 건물×조건 행, 단계별 funnel, 199개 Sheet A/B/C와 HTML gallery다.
- 기존 완료 Roofer output은 재사용하고 미실행 component만 한 번 처리한다.
- R1 15.7GB 입력, Images.zip, OPF.zip은 재해시하지 않는다.
- C4/C5, Fusion W1, held-out, R_ext는 실행하지 않는다.
- G3/G4/PASS는 현 후보 기준의 diagnostic 값만 기록하고 공식 판정은 `null`이다.
- `scientific_verdict`는 사람의 별도 판단 전까지 `null`이다.

## 허용 경로

- `artifacts/manifests/handoffs/P2-W2C-UTARGET199-CONTRACT-RESULTS-RECOVERY-R1-v1/`
- `artifacts/manifests/p2/utarget199_contract_results_v1/`
- `docs/experiments/p2/utarget199_contract_results_v1/`
- `docs/handoffs/returns/P2_C2W_UTARGET199_CONTRACT_RESULTS_RECOVERY_R1_RETURN_v1.md`

그 밖의 연구 계약, 과거 packet/return/receipt, 구현·config는 Experiment Host에서 수정하지 않는다.
