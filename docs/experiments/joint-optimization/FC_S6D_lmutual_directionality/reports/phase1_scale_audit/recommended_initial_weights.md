# FC-S6D Phase 1: Recommended Initial Weights

No training was run. Values come from the A8 checkpoint and a fixed train-view batch set.

- Config: `configs/mutual_loss/fc_screening/fc_s6/A8_no_terrain_terms.yaml`
- Checkpoint: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase1_existing_terms/runs/A8_no_terrain_terms/ckpt/final.pt`
- Fixed train view indices: `0`
- Device: `cuda`
- `G_base`: `3.053229e-01`
- `G_legacy_raw`: `1.817990e-04`
- `G_geo_raw`: `1.815172e-04`
- `G_semcal_raw`: `2.665765e-04`

## Recommended Scale

- `kappa_match_legacy = G_legacy_raw / G_geo_raw`: `1.0015521722275758`
- `kappa_cap_0p05_base = 0.05 * G_base / (lambda_mu * G_geo_raw)`: `841.0302415332421`
- `recommended kappa_geo`: `1.0015521722275758`
- `beta` for `rho_sem=0.02`: `229.06969371822595`
- `beta` for `rho_sem=0.05`: `572.6742342955649`

## Interpretation

- `A8_v2_geo` should start with `mutual_mode=sem2geo` and `w_mutual = 0.1 * kappa_geo`.
- `A8_v2_joint` needs a new default-off semantic calibration implementation before it can be trained.
- The recommended `beta` is numerically large because the raw semcal gradient is small relative to the base gradient; treat this as a scale warning, not permission to launch joint training.
- The semcal audit formula is roof/wall-only and excludes terrain to preserve the accepted A8 terrain-off boundary.
