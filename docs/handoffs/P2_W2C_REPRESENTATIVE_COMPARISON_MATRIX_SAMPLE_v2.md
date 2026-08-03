# P2 대표 3동 정성·정량 비교판 v2

## Handoff metadata

- handoff_id: `P2-W2C-REPRESENTATIVE-COMPARISON-MATRIX-SAMPLE-v2`
- task_id: `P2-REPRESENTATIVE-COMPARISON-MATRIX-SAMPLE-v2`
- direction: `Work Host -> Experiment Host`
- status: `DRAFT`
- source_commit: `TO_BE_FILLED_AFTER_V2_FIX_REVIEW`
- target_branch: `main`
- research canon: `C1C5_CANON_v2` through `DEC-P1-016`
- follows: `P2-W2C-REPRESENTATIVE-COMPARISON-MATRIX-SAMPLE-v1`
- user_approval: `GRANTED — continue the representative qualitative/quantitative sample without stopping`
- scientific_verdict: `null`

## Goal

v1의 유일한 runtime blocker인 Matplotlib 3D screen-label 호출을 고치고, 기존 v1
partial을 수정·삭제·재사용하지 않은 채 새 v2 namespace에서 같은 outcome-free 3동의
정성·정량 비교판을 한 번만 생성한다.

## Exact scope

- 표본: `DEBY_LOD2_4906974`, `DEBY_LOD2_4907176`, `DEBY_LOD2_4906968`
- config: `configs/p2/representative_comparison_matrix_sample_v2/render_v2.json`
- output: `artifact://JointBuildGS/phase-payloads/p2/representative_comparison_matrix_sample_v2/P2-REPRESENTATIVE-COMPARISON-MATRIX-SAMPLE-v2/`
- code change: 2D/3D 공통 `screen_text` helper와 회귀시험만
- 실행: v1과 같은 reuse-only renderer, exact offered commit을 CLI로 바인딩

## Required results

- 3개 건물별 HTML case sheet와 index
- 168개 PNG 모두 독립 UAS 지붕 reference가 실제로 보임
- 그림과 exact panel hash로 연결된 정량 CSV/metric manifest
- C1 metric self-reference와 초록 UAS overlay 역할 분리
- C3 render는 없으면 `OUTPUT_MISSING`, C4/C5는 `NOT_RUN`
- 공식 G3/G4/PASS와 `scientific_verdict`는 `null`

## Prohibitions

- v1 partial 삭제·덮어쓰기·재사용
- Roofer, G2, GS training, metric 재실행
- R1 15.7GB, `Images.zip`, `OPF.zip` 재해시
- C4/C5 performance 실행

## Stop conditions

- v2 final 또는 partial namespace가 이미 존재함
- source/terminal/evaluator Git blob·bytes·SHA 불일치
- 168개 panel slot, roof-reference visible count 또는 metric-panel binding 불일치

## Return

`docs/handoffs/returns/P2_C2W_REPRESENTATIVE_COMPARISON_MATRIX_SAMPLE_RETURN_v2.md`
