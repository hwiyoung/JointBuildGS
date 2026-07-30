# FC-S6D-2 Phase 1: Default-off Equivalence

No new detach implementation was added. FC-S6D-2 uses existing `mutual_mode=sem2geo`.

## Result

`PASS`

## Evidence

- Source gradient audit: `results/FC_S6D_lmutual_directionality/phase1_scale_audit/gradient_scale_audit.csv`
- Legacy raw mutual loss: `0.007945070043206215`
- A8_v2_geo raw mutual loss: `0.007945070043206215`
- Absolute raw-loss difference: `0.0`

The value equality is expected because A8_v2_geo changes the gradient path, not the scalar formula value.
