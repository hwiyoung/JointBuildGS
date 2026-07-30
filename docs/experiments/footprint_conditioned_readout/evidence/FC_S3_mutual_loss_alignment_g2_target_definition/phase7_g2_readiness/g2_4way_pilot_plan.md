# G2 4-Way Pilot Plan

Do not start full G2 training until a readiness gate passes.

## Arms
- Baseline: existing E1-style training without L_mutual or G2.
- Mutual: existing L_mutual schedule/checkpoint family.
- G2-only: structure targets without L_mutual.
- Mutual+G2: revised Mutual plus G2 targets only after M2-M8 ablations identify a safe mutual recipe.

## Gate
- M1 must not be worse than M0 on final F/support/ground metrics, or the revised mutual candidate must recover E1 stability.
- No candidate may hide GroundSurface failure, regress simple cases, or destroy topology.

## Primary Targets
| priority | target | candidate signal |
| --- | --- | --- |
| 1 | ground support stabilization | classwise ground evidence y distribution, support acceptance, wall-ground closure confidence |
| 2 | surface support coverage | accepted/rejected support distribution and confidence calibration |
| 3 | roof grouping consistency | roof cluster continuity and roof-wall adjacency consistency |
| 4 | roof-wall adjacency consistency | roof-wall adjacency graph consistency |
| 5 | wall-ground closure confidence | wall base support and ground plane confidence |
| 6 | low-support face confidence calibration | per-face support confidence and metric-aware calibration |
