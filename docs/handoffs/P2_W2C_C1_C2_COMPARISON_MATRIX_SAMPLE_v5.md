# P2 C1/C2 comparison matrix sample v5 visual correction — DRAFT

- task_id: `P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v5`
- handoff_id: `P2-W2C-C1-C2-COMPARISON-MATRIX-SAMPLE-v5`
- exact source baseline: `719be7a21fb36a716f6a0fe81a9dfe3de9f80608`
- output: `artifact://JointBuildGS/phase-payloads/p2/c1_c2_comparison_matrix_sample_v5/P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v5`
- scientific_verdict: `null`

## Correction scope

v4의 C1/C2 source output과 정량 6행은 그대로 재사용한다. 새 계산은 정성 표시뿐이다.

1. current UAS LiDAR와 동일 획득 드론 RGB 사이에는 `+45.7 m`를 적용하지 않는다.
2. current UAS LiDAR 점은 수직 이동 `0 m`로 투영한다. 별도 구축된 orthometric LoD2 `RoofSurface` roofline은 현재 카메라 frame으로 들어오는 경계에서만 `+45.7 m`를 한 번 적용한다.
3. RAW 행은 `REFERENCE_CONTEXT / NADIR_MEDIUM / NADIR_TIGHT / OBLIQUE_VALIDATION` 네 패널로 구성한다. coverage, near-nadir, oblique의 실제 카메라 세 개를 사용한다.
4. RAW에는 current UAS class 6 cyan, class 2 magenta, 독립 UAS evaluation cell green, 독립 LoD2 `RoofSurface` roofline yellow를 역할별로 표시한다.
5. C1/C2 input에는 해당 sealed `r_derived` footprint를 orange dashed line으로 표시하고, output에는 Roofer roof/wall surface 자체를 표시한다. 네 공간 시점은 동일한 `TOP / OBLIQUE_1 / OBLIQUE_2 / PRINCIPAL_SECTION` viewport를 사용한다.
6. 기존 v1/v2/v4 및 representative v1–v3 partial/final은 삭제·수정·재사용하지 않는다.

## Execution caps

- renderer invocation: `1`
- Roofer invocation: `0`
- G2 invocation: `0`
- GS training: `0`
- metric recomputation: `0`
- C3/C4/C5 method artifact access: `0`
- official G3/G4/PASS_usable: `null`
- scientific_verdict: `null`

## Activation gate

Docker focused tests, same-acquisition datum regression, RAW context-crop checks, actual-image scratch preflight, fresh namespace check, and immutable `000-offered -> 100-accepted` authorization must pass before the one final render.
