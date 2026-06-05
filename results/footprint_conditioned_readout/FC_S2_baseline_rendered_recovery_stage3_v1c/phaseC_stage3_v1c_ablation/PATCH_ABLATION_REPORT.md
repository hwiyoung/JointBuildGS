# Patch Ablation Report

## Branch Decisions

| branch | rows | OK | mean_delta_F | mean_delta_ground_cov | simple_regressions | edge_regressions | decision | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Stage3Algo-v1c-ground | 30 | 30 | -0.004 | -0.001 | 6 | 0 | REJECT | Robust ground branch did not satisfy recovery/no-regression gate. |
| Stage3Algo-v1c-height-definition | 30 | 30 | 0.000 | 0.000 | 0 | 0 | REJECT | No confirmed safe Stage3 algorithm patch for this branch; kept as diagnostic no-op. |
| Stage3Algo-v1c-roof-merge-prune | 30 | 30 | 0.000 | 0.000 | 0 | 0 | REJECT | No confirmed safe Stage3 algorithm patch for this branch; kept as diagnostic no-op. |
| Stage3Algo-v1c-roof-evaluator-matching | 30 | 30 | 0.000 | 0.000 | 0 | 0 | REJECT | No confirmed safe Stage3 algorithm patch for this branch; kept as diagnostic no-op. |
| Stage3Algo-v1c-support-attribution | 30 | 30 | 0.000 | 0.000 | 0 | 0 | REJECT | No confirmed safe Stage3 algorithm patch for this branch; kept as diagnostic no-op. |
| Stage3Algo-v1c-combined-selected | 30 | 30 | 0.000 | 0.000 | 0 | 0 | REJECT | No confirmed safe Stage3 algorithm patch for this branch; kept as diagnostic no-op. |

## Rejection Gates

- Regress good/simple cases: enforced by B0/B1/B2/B8 F and roof coverage deltas.
- Increase open/non-manifold edges: enforced from Metric-v1 topology diagnostics.
- Hide GroundSurface failure: v1c-ground refuses to synthesize ground when explicit class-3 evidence is absent.
- Improve roof_cov by destroying topology: roof merge/prune branch is rejected as no-op.
- Change Stage2 evidence or footprint/domain assumptions: not performed.

## Selected Combination

`v1c-combined-selected` includes only accepted branches. In this run that means `v1c-ground` if its summary decision is ACCEPT; otherwise combined remains identical to Stage3Algo-v1.
