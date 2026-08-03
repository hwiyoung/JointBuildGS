# P2 C1/C2 대표 3동 정성·정량 비교판 v2 Return

## Return metadata

- handoff_id: `P2-W2C-C1-C2-COMPARISON-MATRIX-SAMPLE-v2`
- task_id: `P2-C1-C2-COMPARISON-MATRIX-SAMPLE-v2`
- direction: `Experiment Host -> Work Host`
- technical_state: `BLOCKED_BEFORE_FIRST_PANEL`
- accepted_commit: `1c398211a0862456ed2935676ea15d04fafa48fa`
- scientific_verdict: `null`
- official G3/G4/PASS_usable: `null`

## Returned state

실행 전 Docker tests, exact six-row source binding, C1/C2
`COMPLETED_REUSED_EXACT` terminal binding 및 reference-centered section visibility
`15/332/677`은 통과했다.

renderer는 한 번 호출됐지만 첫 panel 전 projection datum config의 `/configs` mount
부재로 중단됐다. 이는 C1/C2 또는 Roofer 실패가 아니다. v2 final은 없고 생성된 빈
`.partial` directory는 삭제·수정·재사용하지 않고 보존했다.

## Counts

- case sheets: `0`
- PNG panels: `0`
- quantitative rows produced: `0`
- renderer attempts: `1`
- Roofer invocations: `0`
- G2 invocations: `0`
- GS training invocations: `0`
- metric recomputations: `0`
- C3/C4/C5 method-artifact access: `0`

## Recovery boundary

동일 v2 namespace를 재사용하지 않는다. 후속 recovery는 새 packet/task/namespace에서
`/configs:ro` mount를 포함한 exact Docker command로 camera projection까지 미리
검증한 뒤 실행해야 한다.

상세 기록:
`docs/experiments/p2/c1_c2_comparison_matrix_sample_v2/technical_report_ko_v1.md`
