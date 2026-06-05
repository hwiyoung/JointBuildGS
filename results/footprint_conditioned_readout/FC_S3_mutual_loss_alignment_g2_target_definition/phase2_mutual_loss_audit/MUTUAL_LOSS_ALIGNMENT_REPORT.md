# FC-S3 Phase 2: Mutual Loss Alignment Audit

Existing TensorBoard logs were parsed for the requested loss components. Missing component rows are explicit rather than reconstructed from GT semantics.

## Availability
- Mutual scalar tags available: 22.
- Classwise gradient norms: unavailable in existing logs.
- Loss components named roof_wall_relation and ground_wall_relation were not logged as separate TensorBoard scalars.

## Alignment
- Mean final F all 10: E1=0.822, E2=0.803.
- Ground mutual component last-first change: 0.000.
- Bid-level alignment is in loss_to_metric_alignment_by_bid.csv.

## Interpretation
The audit treats lower proxy loss or entropy as insufficient unless it improves final support or geometry metrics under Stage3Algo-v1 + Metric-v1.
