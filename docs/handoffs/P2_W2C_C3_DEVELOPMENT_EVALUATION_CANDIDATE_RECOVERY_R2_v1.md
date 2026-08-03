# P2 W2C C3 development evaluation candidate recovery R2 v1

## Metadata

- handoff_id: `P2-W2C-C3-DEVELOPMENT-EVALUATION-CANDIDATE-RECOVERY-R2-v1`
- task_id: `P2-C3-DEVELOPMENT-EVALUATION-CANDIDATE-v1`
- direction: `Work Host -> Experiment Host`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `c07e812fe0063b386f3efc14b8dd4e9a3b6007e9`
- target_branch: `main`
- research canon: `docs/research/00_RESEARCH_CHARTER.md` through `06_DECISION_LOG.md`
- result contract: `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
- user_approval: `APPROVED_IN_SESSION_2026-08-03_CONTINUE_WITHOUT_STOPPING`
- scientific_verdict: `null`

## 목적과 범위

R1 `000-offered`의 `base_main` 전체 hash 오기를 수정하지 않고 교체한다. Experiment
Host는 R1을 수락하거나 실행하지 않았다. 실행 범위는 이전 recovery packet과 동일하다.

- 완료된 C3 G2 18건을 재사용하고 reconstruction, Roofer, G2를 재실행하지 않는다.
- C3 51행과 기존 C1/C2 102행을 합쳐 단계별 153행 및 조건별 요약을 만든다.
- 사전선정 5동의 실제 UAS/C1/C2/C3 지붕 비교 PNG를 만든다.
- G3/G4는 진단 후보값, 공식 G3/G4/PASS와 `scientific_verdict`는 `null`이다.
- validation 11, held-out 10, C4, C5, Fusion W1, R_ext와 대용량 원본 hash를 열지 않는다.

## 실행 명령

```bash
bash scripts/p2/c3_development_evaluation_candidate_v1/run_evaluation_host.sh \
  /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  c07e812fe0063b386f3efc14b8dd4e9a3b6007e9
```

## Return packet

`docs/handoffs/returns/P2_C2W_C3_DEVELOPMENT_EVALUATION_CANDIDATE_RECOVERY_R2_RETURN_v1.md`
