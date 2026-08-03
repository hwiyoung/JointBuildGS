# P2 C1/C2 대표 3동 정성·정량 비교판 v2 recovery

## Handoff metadata

- handoff_id: `P2-W2C-C1-C2-COMPARISON-MATRIX-SAMPLE-v2`
- task_id: `P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v2`
- direction: `Work Host -> Experiment Host`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `3fa337fd707e3b069182688c8dff481fef93b993`
- target_branch: `main`
- follows: `P2-W2C-C1-C2-COMPARISON-MATRIX-SAMPLE-v1`
- research canon: `C1C5_CANON_v2` through `DEC-P1-016`
- user_approval: `GRANTED — complete C1/C2 results without recomputing Roofer`
- implementation_review: `PASS — Docker focused renderer tests 14/14; exact C1/C2-only 60-panel and reference-centered-section regression`
- experiment_host_preflight: `PASS — exact source hashes; 6 C1/C2 rows; 2 unique sealed operation units; terminal COMPLETED_REUSED_EXACT; section visible 15/332/677; v2 final/partial namespaces absent`
- scientific_verdict: `null`

## Exact recovery

v1의 bbox-centered principal section만 고친다. 모든 C1/C2 input/output 단면은 동일한
독립 roof reference XY median을 통과하고, 주축 방향과 band 폭은 v1과 같다. 이 선택은
metric, gate 또는 method output을 보지 않는다.

- config: `configs/p2/c1_c2_comparison_matrix_sample_v2/render_v2.json`
- output: `artifact://JointBuildGS/phase-payloads/p2/c1_c2_comparison_matrix_sample_v2/P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v2/`
- exact same 3 buildings, 60 PNG, 6 quantitative rows
- v1 partial을 삭제·수정·재사용하지 않는다.
- C3–C5, Roofer, G2, GS training, metric 재계산은 모두 0이다.
- official G3/G4/PASS와 scientific_verdict는 `null`이다.

Docker regression과 exact source/output-namespace preflight 뒤 새 namespace에서 한 번만
실행한다.
