# P2 W2C C3 development evaluation candidate v1

## Metadata

- handoff_id: `P2-W2C-C3-DEVELOPMENT-EVALUATION-CANDIDATE-v1`
- task_id: `P2-C3-DEVELOPMENT-EVALUATION-CANDIDATE-v1`
- direction: `Work Host -> Experiment Host`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `714893724575cc739e530cf97c9897a8a4792275`
- target_branch: `main`
- research canon: `docs/research/00_RESEARCH_CHARTER.md` through `06_DECISION_LOG.md`, `C1C5_CANON_v2`, `DEC-P1-014`
- result contract: `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
- user_approval: `APPROVED_FOR_EXECUTION`
- scientific_verdict: `null`

## 목적

기존 C1/C2 결과와 방금 생성한 C3 Roofer 결과를 재실행 없이 평가해, 지금까지
비어 있던 정량값과 실제 모델 비교 그림을 만든다.

1. C3 unique CityJSONSeq 18개에 pinned val3dity 2.6.0을 실행해 G2를 계산한다.
2. 동일 development 51동의 독립 UAS score cells로 C3 roof-plane 구조 지표와
   높이·표면 거리 지표를 계산한다.
3. C1/C2 기존 102행과 C3 51행을 합친 153행 진단표와 조건별 단계표를 만든다.
4. outcome-free 사전선정 5동의 UAS/C1/C2/C3 실제 RoofSurface top/oblique 비교
   PNG를 만든다.

## 해석 경계

- G2는 고정된 val3dity 계약에 따른 실제 boolean이다.
- G3/G4는 현재 문서에 이미 기록된 후보 matcher와 후보 threshold를 적용한
  `G3_candidate`, `G4_candidate`이다.
- G3 matcher 검증과 G4 허용 기준이 아직 동결되지 않았으므로 공식
  `G3_roof_structure_acceptable`, `G4_geometric_accuracy_acceptable`,
  `PASS_usable`은 `null`로 유지한다.
- 후보 통과 수는 임계값 동결을 위한 사람의 검토 입력이며 과학적 결론이 아니다.

## 재사용과 금지

- C1/C2 reconstruction·Roofer·연속 metric은 재실행하지 않는다.
- C3 surface·Roofer도 재실행하지 않고 terminal receipt를 검증해 재사용한다.
- R1 15.7GB, Images.zip, OPF.zip은 해시하지 않는다.
- validation 11, held-out 10, C4, C5, Fusion W1, R_ext는 열지 않는다.
- 평가용 UAS cells와 building ID는 geometry 생성에 사용하지 않는다.
- shared component는 건물 bbox 안의 평가 cell에서만 점수화하며 C3 geometry를
  자르거나 다시 만들지 않는다.

## 실행 명령

```bash
bash scripts/p2/c3_development_evaluation_candidate_v1/run_evaluation_host.sh \
  /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  714893724575cc739e530cf97c9897a8a4792275
```

## 필수 결과

- `results/c3_development_diagnostics_v1.jsonl` — C3 51행
- `results/three_condition_development_diagnostics_v1.jsonl` — C1/C2/C3 153행
- `results/three_condition_summary_v1.jsonl` — 조건별 단계·후보 통과 수
- `qualitative/*_C1_C2_C3_roof_comparison_v1.png` — 사전선정 5동
- 한국어 결과 보고서, compact manifest, Return Packet
- `scientific_verdict: null`

## Return packet

`docs/handoffs/returns/P2_C2W_C3_DEVELOPMENT_EVALUATION_CANDIDATE_RETURN_v1.md`
