# P2 W2C C1 baseline audit v1

## Metadata

- handoff_id: `P2-W2C-C1-BASELINE-AUDIT-v1`
- task_id: `P2-C1-BASELINE-AUDIT-v1`
- direction: `Work Host -> Experiment Host`
- status: `DRAFT`
- source_commit: `ae8288b2206e40949050ae7967c411c7b034449d`
- target_branch: `main`
- research canon: `docs/research/00_RESEARCH_CHARTER.md` through `06_DECISION_LOG.md`
- result contract: `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
- scientific_verdict: `null`

## 왜 하는가

기존 evaluator가 C1을 self-reference라는 이유로 G2–G4 전체에서 제외한 것은 과도했다.
C1도 Roofer 산출물 자체의 G2를 통과해야 하며, G3/G4는 독립 정확도 주장이 아닌
`SELF_REFERENCE_DIAGNOSTIC_ONLY` 분포로 보고해야 한다.

## 한정된 실행

1. 기존 C1 Roofer CityJSONSeq 1개에 pinned val3dity를 1회 실행한다.
2. 기존 development 51동 UAS score cell과 연속 지표를 다시 계산하지 않고 읽는다.
3. C1 G3/G4 후보 진단과 51행 요약을 만든다.
4. C1 input과 geometry reference의 동일 계보, 51동이 하나의 Roofer output을 공유한다는
   사실을 결과 해석에 명시한다.
5. 기존 5개 PNG와 함께 입력·처리·결과가 한눈에 보이는 한국어 결과 설명서를 갱신한다.

## 금지

- C1 reconstruction 또는 Roofer 재실행
- C2/C3/C4/C5 실행·수정
- validation/held-out 접근
- R1, Images.zip, OPF.zip 재해시
- C1 G3/G4를 독립 성능이나 공식 PASS로 승격

## 실행 명령

```bash
bash scripts/p2/c1_baseline_audit_v1/run_audit_host.sh \
  /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774
```

## 필수 결과

- C1 51행 G2 및 self-reference G3/G4 진단
- C1 baseline을 threshold calibration에 사용할 수 있는 범위와 한계
- 간단한 한국어 결과 보고서와 Return Packet
- 공식 G3/G4/PASS 및 `scientific_verdict: null`
