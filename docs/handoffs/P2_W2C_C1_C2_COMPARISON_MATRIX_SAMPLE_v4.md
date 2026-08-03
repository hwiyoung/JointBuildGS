# P2 C1/C2 대표 3동 정성·정량 비교판 v4 recovery

## Handoff metadata

- handoff_id: `P2-W2C-C1-C2-COMPARISON-MATRIX-SAMPLE-v4`
- task_id: `P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v4`
- direction: `Work Host -> Experiment Host`
- status: `DRAFT_PENDING_TEST_AND_ACTIVATION`
- source_commit: `PENDING`
- target_branch: `main`
- follows: `P2-W2C-C1-C2-COMPARISON-MATRIX-SAMPLE-v2`
- research canon: `C1C5_CANON_v2` through `DEC-P1-016`
- user_approval: `GRANTED — proceed with a new recovery namespace after preserving the v2 empty partial`
- scientific_verdict: `null`

## Exact recovery

v2는 첫 panel 전에 canonical repository mount가 아닌 `/workspace` mount를 사용해
projection datum 기본 config가 `/configs/input_and_alignment/projection_datum.json`으로
해석되면서 중단됐다. v4는 repository를 project image의 canonical path
`/workspace/JointBuildGS:ro`에 mount하고 동일한 배치에서 camera projection preflight와
본 renderer를 수행한다. renderer 구현과 reference-centered section 선택은 바꾸지 않는다.

- config: `configs/p2/c1_c2_comparison_matrix_sample_v4/render_v4.json`
- renderer: `scripts/p2/representative_comparison_matrix_sample_v1/render_sample.py`
- output: `artifact://JointBuildGS/phase-payloads/p2/c1_c2_comparison_matrix_sample_v4/P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v4/`
- exact same 3 buildings, 60 PNG, 6 quantitative rows
- existing v1/v2 partial과 다른 representative v1/v2/v3 partial을 삭제·수정·재사용하지 않는다.
- C3–C5 method artifact, Roofer, G2, GS training, metric 재계산은 모두 0이다.
- official G3/G4/PASS와 scientific_verdict는 `null`이다.

## Runtime lock

- repository mount: `/workspace/JointBuildGS:ro`
- workdir: `/workspace/JointBuildGS`
- artifact mount: `/artifacts/JointBuildGS`
- image: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- projection config resolved path: `/workspace/JointBuildGS/configs/input_and_alignment/projection_datum.json`

새 final/partial namespace의 부재를 확인하고, 실제 실행과 동일한 image/mount/workdir로
세 건물의 raw-camera projection 및 reference-centered principal section visible count가
모두 0보다 큰지 read-only로 확인한 뒤 output namespace를 한 번만 생성한다.
