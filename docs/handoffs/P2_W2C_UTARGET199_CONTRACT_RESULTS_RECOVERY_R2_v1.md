# P2 W2C U_target 199 contract results recovery R2 v1

## Metadata

- handoff_id: `P2-W2C-UTARGET199-CONTRACT-RESULTS-RECOVERY-R2-v1`
- task_id: `P2-UTARGET199-CONTRACT-RESULTS-RECOVERY-R2-v1`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `5747f2abd492215b598888d7ab6b9b9cd4bcb1f2`
- explicit_user_authorization: `APPROVED_IN_SESSION_TO_CONTINUE_UTARGET199_EXECUTION`
- predecessor: `P2-W2C-UTARGET199-CONTRACT-RESULTS-RECOVERY-R1-v1/300-closed.json`
- scientific_verdict: `null`

## 목적과 범위

R1에서 고정된 74개 Roofer terminal과 74개 G2 receipt를 재사용한다. Roofer와 G2는
한 번도 다시 실행하지 않고, 이미 검증된 CityJSONSeq empty-header parser로 597행을
최종화한 뒤 199개 Sheet A/B/C와 HTML gallery를 생성한다.

- 199동 × C1/C2/C3 = 597행을 모두 유지한다.
- `ONE_TO_ONE`, `SHARED`, `MULTI`, `UNASSOCIATED`를 숨기지 않고 단계별 funnel에 기록한다.
- 74개 결과를 199동별 독립 생성 성공으로 표현하지 않는다.
- R1, Images.zip, OPF.zip, checkpoint는 재해시하지 않는다.
- 199개 그림 생성을 위한 checkpoint safe-deserialization은 1회만 허용한다.
- G3/G4/PASS는 diagnostic candidate이며 공식 판정과 `scientific_verdict`는 `null`이다.
- C4/C5, Fusion W1, R_ext는 실행하지 않는다.

Experiment Host는 recovery receipt/result/Return 경로만 수정할 수 있으며 과거 계보와
연구 계약·구현은 수정하지 않는다.
