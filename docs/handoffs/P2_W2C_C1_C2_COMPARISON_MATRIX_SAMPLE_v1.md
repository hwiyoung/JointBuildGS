# P2 C1/C2 대표 3동 정성·정량 비교판 v1

## Handoff metadata

- handoff_id: `P2-W2C-C1-C2-COMPARISON-MATRIX-SAMPLE-v1`
- task_id: `P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v1`
- direction: `Work Host -> Experiment Host`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `e5c5e44d4fd074d1513b80a4a46063281539ddd3`
- target_branch: `main`
- research canon: `C1C5_CANON_v2` through `DEC-P1-016`
- user_approval: `GRANTED — C1/C2 qualitative and quantitative results first`
- implementation_review: `PASS — exact method-subset, panel-count and no-C3 regression checks`
- experiment_host_preflight: `PASS — 6 rows, 2 unique sealed units, new namespace absent`
- scientific_verdict: `null`

## Goal

요청한 순서대로 current raw image 4개, C1 LiDAR input/output, C2 MVS input/output을
동일 건물·동일 TOP/OBLIQUE_1/OBLIQUE_2/PRINCIPAL_SECTION 시점에 놓고, 각 output에
exact 대응하는 정량값을 같은 comparison matrix에 결합한다.

## Exact sample and output

v3에서 outcome 없이 고정한 서로 다른 3개 group의 small/medium/large 표본을 그대로
사용한다: `DEBY_LOD2_4907177`, `DEBY_LOD2_4906975`, `DEBY_LOD2_108580336`.

- config: `configs/p2/c1_c2_comparison_matrix_sample_v1/render_v1.json`
- output: `artifact://JointBuildGS/phase-payloads/p2/c1_c2_comparison_matrix_sample_v1/P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v1/`
- 3 case sheets, 60 PNG, panel/metric/projection manifests, exact 6-row quantitative CSV
- C1 self-reference metric과 독립 UAS overlay의 역할을 분리 표시
- C2는 independent UAS score-only reference와 exact 같은 output/support를 표시

## Execution boundary

- sealed U_target 결과와 source terminal을 읽어 후처리만 한다.
- C3–C5 source를 읽거나 표시하지 않는다.
- Roofer, G2, GS training, metric을 실행하거나 재계산하지 않는다.
- v1/v2/v3 partial을 삭제·수정·재사용하지 않는다.
- official G3/G4/PASS 또는 scientific verdict를 결정하지 않는다.

## Activation

Docker focused test, source-binding preflight, exact offered commit과 immutable
`100-accepted` receipt가 모두 맞은 뒤 Experiment Host에서 새 namespace를 한 번만 만든다.
