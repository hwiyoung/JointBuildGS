# FC-S6E Phase 1: Recommended Joint Weights

No training was run for this audit.

- Config base: `configs/mutual_loss/fc_screening/fc_s6/A8_no_terrain_terms.yaml`
- Checkpoint: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase1_existing_terms/runs/A8_no_terrain_terms/ckpt/final.pt`
- Fixed train view indices: `0`
- Device: `cuda`
- `G_base`: `3.053230e-01`
- `G_legacy_raw`: `1.817990e-04`
- `G_geo_raw`: `1.815172e-04`
- `G_semcal_raw`: `2.483893e-04`
- `kappa_geo`: `1.0015521722275758`
- effective `beta` for `rho_sem=0.02`: `245.8423272814571`
- effective `beta` for `rho_sem=0.05`: `614.6058182036428`
- train-config `mutual_semcal_weight_beta` for 2pct: `245.46132902360284`

The train path uses `w_mutual=lambda*kappa_geo`, so the config beta is divided by `kappa_geo` to keep the effective semantic calibration coefficient at `lambda*beta`.

Primary runnable candidate: `A8_v2_joint_2pct`.
Do not run 5pct unless the 2pct run is stable but too weak.
