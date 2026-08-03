# P2 C2W C3 development evaluation candidate recovery R2 Return v1

- handoff_id: `P2-W2C-C3-DEVELOPMENT-EVALUATION-CANDIDATE-RECOVERY-R2-v1`
- task_id: `P2-C3-DEVELOPMENT-EVALUATION-CANDIDATE-v1`
- writer: Experiment Host
- return direction: Experiment Host -> Work Host
- return state: `DIAGNOSTICS_COMPLETE`
- source commit: `c07e812fe0063b386f3efc14b8dd4e9a3b6007e9`
- offered commit: `4a46b38bac1403882a7bf0f0e457d7989e71b965`
- accepted commit: `a3684031fa466538fa6763bd8029c070ab5f3ab8`
- scientific_verdict: `null`

## 반환 결과

동일한 development 51동에서 C1/C2/C3 각 51행, 총 153행의 단계별 결과와 사전선정
5동의 실제 UAS/C1/C2/C3 비교 PNG를 생성했다. C2는 G0/G1/G2가 각각 50/50/50,
C3는 평가 component 관점 G0/G1이 35/37이고 G2가 19다. C3에서 엄격한 건물↔component
1:1 연결은 6동뿐이다.

G3 후보는 C2/C3 모두 0, G4 후보는 C2 6, C3 1, 후보 교집합은 모두 0이다. 다만
G3 matcher와 G4 threshold가 동결되지 않았으므로 이 숫자는 진단용이며 공식
`PASS_usable`과 `scientific_verdict`는 `null`이다.

## 반환 기록

- 한국어 보고서: `docs/experiments/p2/c3_development_evaluation_candidate_recovery_r2_v1/TECHNICAL_RETURN_REPORT_v1.md`
- compact manifest: `artifacts/manifests/p2/c3_development_evaluation_candidate_recovery_r2_v1/technical_result_manifest_v1.json`
- 외부 결과: `artifact://JointBuildGS/phase-payloads/p2/c3_development_evaluation_candidate_v1/P2-C3-DEVELOPMENT-EVALUATION-CANDIDATE-v1/`

재구성, Roofer, G2는 재실행하지 않았고 대용량 R1/Images.zip/OPF.zip도 다시 hash하지
않았다. validation/held-out/C4/C5/Fusion W1/R_ext 접근은 없었다. Experiment Host는
200-verified와 direct-child 300-closed를 게시해 writer를 Work Host로 반환한다.
