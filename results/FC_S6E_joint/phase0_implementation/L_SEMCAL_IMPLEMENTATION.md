# FC-S6E Phase 0: L_semcal Implementation

## Status

`IMPLEMENTED_DEFAULT_OFF`

## Scope

- Added optional roof/wall-only `L_semcal` inside `src/stage2/loss/mutual.py`.
- Training integration is controlled by config flags in `src/stage2/train.py`.
- Terrain semantic calibration remains disabled for FC-S6E.
- Lmu7, Lmu8, L_structure, G2, Stage3, and Metric-v1 are not modified.

## Config Flags

- `mutual_semcal_enabled`: default `false`
- `mutual_semcal_classes`: default `roof_wall`
- `mutual_semcal_tau`: geometry cue temperature
- `mutual_semcal_weight_beta`: beta inside the mutual raw total
- `mutual_semcal_reliability_gate`: `none|confidence|entropy|conf_entropy`
- `mutual_semcal_entropy_tau`, `mutual_semcal_entropy_alpha`: entropy gate shape

## Formula

`p_rw = normalize([p_roof, p_wall])`

`score_roof = exp(-relu(tau - (n dot g)^2)^2 / tau_geom)`

`score_wall = exp(-(n dot g)^2 / tau_geom)`

`s_geom = normalize([score_roof, score_wall])`

`L_semcal = mean stopgrad(reliability) * KL(stopgrad(s_geom) || p_rw)`

## Effective Training Scale

The train path uses `loss += w_mutual * (L_geo + beta_cfg * L_semcal)`.
For FC-S6E, `w_mutual = lambda_mu * kappa_geo`, so `beta_cfg = beta_effective / kappa_geo`.
