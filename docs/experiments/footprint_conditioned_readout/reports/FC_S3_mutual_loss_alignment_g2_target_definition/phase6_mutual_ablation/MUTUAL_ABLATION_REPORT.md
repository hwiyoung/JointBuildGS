# FC-S3 Phase 6: Mutual Reweighting and Ablation Planning

Full retraining is not started in FC-S3. M0 and M1 use existing checkpoints; M2-M8 are concrete ablation candidates.

## Cheapest Diagnostic Subset
1. M5: remove ground/terrain term to directly test B104-like failures.
2. M3: reduce mutual weight to 0.25x to test whether E1-like stability returns.
3. M4: roof-wall only to test whether roof cases benefit without ground transfer.

## Existing Stage3 Result
- M0 mean F all 10: 0.822.
- M1 mean F all 10: 0.803.

Do not claim Mutual-alone final improvement unless M1 beats M0 on final read-out metrics.
