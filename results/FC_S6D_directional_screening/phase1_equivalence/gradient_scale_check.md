# FC-S6D-2 Phase 1: Gradient Scale Check

- Source: `results/FC_S6D_lmutual_directionality/phase1_scale_audit/gradient_scale_audit.csv`
- Weight recommendation: `results/FC_S6D_lmutual_directionality/phase1_scale_audit/recommended_initial_weights.md`

## Key Check

- A8_v2_geo semantic-logit mutual grad norm: `0.0`
- A8_v2_geo rotation/normal proxy grad norm: `0.0001814754616020494`
- A8_v2_geo center/height proxy grad norm: `3.893508055894205e-06`
- A8_v2_geo weighted grad ratio to base: `5.9450893408002155e-05`

Interpretation: `sem2geo` removes semantic-logit gradient through mutual class weights while preserving nonzero geometry gradients.
