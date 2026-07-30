# FC-S6E Phase 0: Default-off Equivalence

## Result

`PASS`

- Random fixed-batch mutual scalar difference with semcal default-off: `0.000000000000e+00`
- Existing defaults keep `mutual_semcal_enabled=false` and `mutual_semcal_weight_beta=0.0`.
- No additional backward path is active unless the flag and beta are explicitly set.
