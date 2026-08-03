# P2 W2C C3 development evaluation candidate recovery v1

## Metadata

- handoff_id: `P2-W2C-C3-DEVELOPMENT-EVALUATION-CANDIDATE-RECOVERY-v1`
- task_id: `P2-C3-DEVELOPMENT-EVALUATION-CANDIDATE-v1`
- direction: `Work Host -> Experiment Host`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `c07e812fe0063b386f3efc14b8dd4e9a3b6007e9`
- target_branch: `main`
- research canon: `docs/research/00_RESEARCH_CHARTER.md` through `06_DECISION_LOG.md`, `C1C5_CANON_v2`, `DEC-P1-014`
- result contract: `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
- user_approval: `APPROVED_IN_SESSION_2026-08-03_CONTINUE_WITHOUT_STOPPING`
- scientific_verdict: `null`

## 목적

첫 실행에서 이미 완료한 C3 CityJSON 18개의 val3dity 결과를 그대로 재사용하고,
권한 문제로 중단된 최종 집계와 정성 비교판만 복구한다. 재구성, Roofer, G2는 다시
실행하지 않는다.

1. 기존 C3 51행과 완료된 G2 18건을 검증해 읽는다.
2. C3 G3/G4 진단 후보값을 계산한다.
3. 기존 C1/C2 102행과 합쳐 C1/C2/C3 153행의 단계별 표와 조건별 요약을 만든다.
4. 결과를 보지 않고 미리 고른 5개 건물의 UAS/C1/C2/C3 실제 지붕 모델 비교 PNG를 만든다.

## 해석 경계

- G2는 고정된 val3dity 계약에 따른 실제 boolean이다.
- G3/G4는 현재 문서에 기록된 후보 matcher와 후보 threshold를 적용한 진단값이다.
- matcher 검증과 수치 임계값 동결 전까지 공식 `G3_roof_structure_acceptable`,
  `G4_geometric_accuracy_acceptable`, `PASS_usable`은 `null`로 둔다.
- 후보 통과 수는 사람의 임계값 검토를 돕는 진단 결과이며 과학적 판정이 아니다.

## 재사용·금지 계약

- 기존 partial namespace의 준비 파일과 18개 G2 terminal receipt를 exact reuse한다.
- C1/C2 reconstruction, Roofer, 기존 metric을 재실행하지 않는다.
- C3 surface 생성과 Roofer를 재실행하지 않는다.
- R1 15.7GB 입력, Images.zip, OPF.zip을 다시 해시하지 않는다.
- validation 11, held-out 10, C4, C5, Fusion W1, R_ext를 열지 않는다.
- 평가용 UAS와 building ID를 geometry 생성에 사용하지 않는다.

## 실행 명령

```bash
bash scripts/p2/c3_development_evaluation_candidate_v1/run_evaluation_host.sh \
  /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  c07e812fe0063b386f3efc14b8dd4e9a3b6007e9
```

## 필수 결과

- `results/c3_development_diagnostics_v1.jsonl`: C3 51행
- `results/three_condition_development_diagnostics_v1.jsonl`: C1/C2/C3 153행
- `results/three_condition_summary_v1.jsonl`: 조건별 단계·후보 통과 수와 의미
- `qualitative/*_C1_C2_C3_roof_comparison_v1.png`: 사전선정 5동
- 한국어 기술 결과 보고서, compact manifest, Return Packet
- `scientific_verdict: null`

## Return packet

`docs/handoffs/returns/P2_C2W_C3_DEVELOPMENT_EVALUATION_CANDIDATE_RECOVERY_RETURN_v1.md`
