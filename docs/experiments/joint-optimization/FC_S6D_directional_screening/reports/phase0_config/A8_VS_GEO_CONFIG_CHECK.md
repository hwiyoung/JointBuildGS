# FC-S6D-2 Phase 0: A8 vs A8_v2_geo Config Check

## Verdict

`PASS`

## Inputs
- A8 config: `configs/mutual_loss/fc_screening/fc_s6/A8_no_terrain_terms.yaml`
- A8_v2_geo source config: `configs/mutual_loss/fc_screening/fc_s6d/A8_v2_geo.yaml`
- A8_v2_geo screening config: `results/FC_S6D_directional_screening/configs/A8_v2_geo.yaml`

## Confirmed Active Terms

- wall verticality: ON
- roof non-wall prior: ON
- roof-side height: ON
- terrain normal: OFF
- terrain-side height: OFF

## Directionality

- A8 legacy uses `mutual_mode=full`.
- A8_v2_geo uses `mutual_mode=sem2geo`, which detaches class probabilities in `src/stage2/loss/mutual.py`.
- A8_v2_geo uses `kappa_geo=1.0015521722275758` from FC-S6D gradient audit.

## Disabled Items

- Lmu7 roof-wall hint: disabled
- Lmu8 terrain-wall hint: disabled
- L_structure: disabled
- G2: not invoked
- A8_v2_joint: not run
