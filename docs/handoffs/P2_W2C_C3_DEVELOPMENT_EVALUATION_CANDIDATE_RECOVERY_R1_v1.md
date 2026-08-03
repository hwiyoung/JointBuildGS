# P2 W2C C3 development evaluation candidate recovery R1 v1

## Metadata

- handoff_id: `P2-W2C-C3-DEVELOPMENT-EVALUATION-CANDIDATE-RECOVERY-R1-v1`
- task_id: `P2-C3-DEVELOPMENT-EVALUATION-CANDIDATE-v1`
- direction: `Work Host -> Experiment Host`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `c07e812fe0063b386f3efc14b8dd4e9a3b6007e9`
- target_branch: `main`
- research canon: `docs/research/00_RESEARCH_CHARTER.md` through `06_DECISION_LOG.md`, `C1C5_CANON_v2`, `DEC-P1-014`
- result contract: `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
- user_approval: `APPROVED_IN_SESSION_2026-08-03_CONTINUE_WITHOUT_STOPPING`
- scientific_verdict: `null`

## 교체 사유

직전 recovery의 `000-offered`는 artifact availability enum 오기로 validation에
실패했고 Experiment Host가 수락하지 않았다. 그 receipt는 수정하지 않는다. 이 R1은
동일한 bounded recovery를 올바른 receipt로 다시 제안한다.

## 목적과 범위

- 기존 partial namespace의 준비 파일과 완료된 G2 18건을 exact reuse한다.
- C3 51행의 G2와 G3/G4 진단 후보값을 집계한다.
- 기존 C1/C2 102행과 합쳐 C1/C2/C3 153행 단계별 표와 조건별 요약을 만든다.
- 결과를 보지 않고 미리 고른 5개 건물의 UAS/C1/C2/C3 실제 모델 비교 PNG를 만든다.
- reconstruction, Roofer, G2, R1 대용량 입력 hash를 다시 실행하지 않는다.
- validation 11, held-out 10, C4, C5, Fusion W1, R_ext를 열지 않는다.

## 해석 경계

G2는 공식 boolean이다. G3/G4는 matcher·threshold 동결 전 진단 후보값이므로 공식
`G3_roof_structure_acceptable`, `G4_geometric_accuracy_acceptable`,
`PASS_usable`은 `null`로 유지한다. `scientific_verdict`도 `null`이다.

## 실행 명령

```bash
bash scripts/p2/c3_development_evaluation_candidate_v1/run_evaluation_host.sh \
  /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  c07e812fe0063b386f3efc14b8dd4e9a3b6007e9
```

## 필수 결과

- C3 51행, C1/C2/C3 153행, 조건별 요약
- 사전선정 5동의 실제 UAS/C1/C2/C3 roof comparison PNG
- 한국어 기술 결과 보고서, compact manifest, Return Packet

## Return packet

`docs/handoffs/returns/P2_C2W_C3_DEVELOPMENT_EVALUATION_CANDIDATE_RECOVERY_R1_RETURN_v1.md`
