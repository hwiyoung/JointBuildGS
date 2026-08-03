# P2 대표 3동 정성·정량 비교판 v3

## Handoff metadata

- handoff_id: `P2-W2C-REPRESENTATIVE-COMPARISON-MATRIX-SAMPLE-v3`
- task_id: `P2-REPRESENTATIVE-COMPARISON-MATRIX-SAMPLE-v3`
- direction: `Work Host -> Experiment Host`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `6cefb12a3b58b53e2554ea676bf40e02149911d0`
- target_branch: `main`
- research canon: `C1C5_CANON_v2` through `DEC-P1-016`
- follows: `P2-W2C-REPRESENTATIVE-COMPARISON-MATRIX-SAMPLE-v2`
- user_approval: `GRANTED — continue the representative qualitative/quantitative sample without stopping`
- independent_review: `PASS — source-availability preflight and scientific-leakage reviews`
- scientific_verdict: `null`

## Goal

v1·v2 partial을 건드리지 않고, strict independent UAS reference와 C1/C2/C3 sealed
operation unit 가용성을 모두 만족하는 outcome-free 표본 3동으로 비교판을 완성한다.

## Exact sample

| size | building | group | bbox area m² |
|---|---|---|---:|
| small | `DEBY_LOD2_4907177` | `GROUP_681774d532569646` | 177.062 |
| medium | `DEBY_LOD2_4906975` | `GROUP_ccf535781f75c1c0` | 2,755.039 |
| large | `DEBY_LOD2_108580336` | `GROUP_ca1040234a79aaa8` | 13,525.446 |

선정에는 strict reference, 세 방법의 봉인 source 가용성, bbox 크기와 서로 다른 공간
group만 사용했다. metric, gate, PASS, 그림은 사용하지 않았다.

## Execution contract

- config: `configs/p2/representative_comparison_matrix_sample_v3/render_v3.json`
- output: `artifact://JointBuildGS/phase-payloads/p2/representative_comparison_matrix_sample_v3/P2-REPRESENTATIVE-COMPARISON-MATRIX-SAMPLE-v3/`
- output namespace 생성 전에 exact 3×3 operation unit을 모두 검증한다.
- 3 case sheets, 168 PNG, 정량 CSV와 panel/metric/projection manifests를 생성한다.
- 모든 panel에 독립 UAS 지붕 reference가 실제로 보여야 한다.
- C1 self-reference metric과 독립 UAS overlay를 분리하고, C3 render missing과 C4/C5
  `NOT_RUN`을 정직하게 표시한다.

## Prohibitions

- v1/v2 partial 삭제·수정·재사용
- Roofer, G2, GS training, metric 또는 C4/C5 실행
- R1 15.7GB, `Images.zip`, `OPF.zip` 재해시
- official G3/G4/PASS 또는 scientific verdict 결정

## Return

`docs/handoffs/returns/P2_C2W_REPRESENTATIVE_COMPARISON_MATRIX_SAMPLE_RETURN_v3.md`
