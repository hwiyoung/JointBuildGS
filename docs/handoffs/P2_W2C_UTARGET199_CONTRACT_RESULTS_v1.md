# P2 W2C U_target 199 contract results v1

## Metadata

- handoff_id: `P2-W2C-UTARGET199-CONTRACT-RESULTS-v1`
- task_id: `P2-UTARGET199-CONTRACT-RESULTS-v1`
- direction: `Work Host -> Experiment Host`
- status: `DRAFT`
- source_commit: `TO_BE_BOUND`
- target_branch: `main`
- research canon: `docs/research/00_RESEARCH_CHARTER.md` through `06_DECISION_LOG.md`
- result contract: `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
- user approval: `GRANTED_IN_SESSION_FOR_UTARGET_199_FULL_EXECUTION`
- scientific_verdict: `null`

## 목적

기존 72/51 사전 필터를 실행 분모로 사용하지 않고 `U_target=199` 전 건물을
C1/C2/C3의 동일 분모로 유지한다. 입력·reference 부족과 방법 실패를 숨기지 않고
단계별 수치, 최종 diagnostic candidate 수와 사람이 확인할 Sheet A/B/C를 생성한다.

## 실행 범위

1. 동결된 C1/C2 228개와 C3 200개 component job을 재사용한다.
2. 199동 bbox는 geometry와 `R_derived`가 봉인된 뒤 identity/display association에만
   사용한다. scientific geometry는 crop·registration·수정하지 않는다.
3. 199동 모두 C1/C2/C3 결과 행을 만든다. reference가 없어도 행과 그림을 남긴다.
4. 과거 완료 Roofer output은 exact reuse하고 미완료 selected component만 한 번 실행한다.
5. unique output별 G2를 pinned val3dity 2.6.0으로 실행한다.
6. UAS candidate reference를 한 stream으로 읽어 continuous metric과 diagnostic
   G3/G4/PASS candidate를 계산한다. 공식 G3/G4/PASS는 null이다.
7. 199동 각각 current RGB, native/input, exact class 2/6 Roofer input와 `R_derived`,
   LoD2 top/oblique/section, UAS overlay, metric/gate strip을 가진 Sheet A/B/C PNG와
   HTML gallery를 만든다.

## 필수 산출물

- 597행 `building_method_metrics_v1.jsonl`
- 597행 `building_acceptance_gates_v1.csv`
- `method_summary_v1.csv`, `gate_funnel_v1.csv`, `population_funnel_v1.csv`
- 199개 `*_Sheet_ABC_v1.png`
- `qualitative/index.html`과 figure manifest
- compact technical manifest와 필수 Return Packet

## 금지

- C1/C2 component 재생성, C3 재학습 또는 checkpoint 변경
- 이미 완료된 Roofer unit 중복 실행
- `R1`, `Images.zip`, `OPF.zip` 전수 재해시
- C4/C5 성능, Fusion W1, R_ext 실행
- LoD2-derived LoD1을 primary C5 또는 독립 reference로 승격
- official G3/G4/PASS 또는 scientific verdict 생성

## 실행 명령

```bash
bash scripts/p2/utarget199_contract_results_v1/run_contract_host.sh \
  /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts \
  sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774 \
  <SOURCE_COMMIT> \
  P2-UTARGET199-CONTRACT-RESULTS-v1
```
