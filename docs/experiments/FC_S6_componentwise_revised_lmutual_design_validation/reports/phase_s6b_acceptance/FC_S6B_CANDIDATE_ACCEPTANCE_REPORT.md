# FC-S6b Candidate Acceptance Report

## Decision

Selected label: `ACCEPT_A8_TERRAIN_OFF`.

A8_no_terrain_terms is the highest-F passing candidate and has the strongest mean ground coverage among the passing top candidates.

This is candidate acceptance for the next controlled pilot, not a final claim that revised `L_mutual` is universally optimal.

## Candidate Split Summary

| Arm | all_10 F | easy_control F | hard_diagnostic F | roof_complex F | terrain_sensitive F | mean ground_cov | mean support_cov | mean ground_support_cov | open/nonmanifold |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 0.820763 | 0.948121 | 0.693405 | 0.523314 | 0.945801 | 0.943933 | 0.472967 | 0.1826 | 0/0 |
| Original Mutual | 0.806918 | 0.919464 | 0.694372 | 0.515009 | 0.950969 | 0.869667 | 0.4568 | 0.1861 | 0/0 |
| A4 terrain-normal-only | 0.828087 | 0.949946 | 0.706229 | 0.538565 | 0.949563 | 0.8844 | 0.481133 | 0.1806 | 0/0 |
| A8 no terrain terms | 0.828707 | 0.952138 | 0.705276 | 0.534607 | 0.950797 | 0.984767 | 0.467 | 0.1723 | 0/0 |
| B2 terrain confidence-gated | 0.822267 | 0.944122 | 0.700411 | 0.526411 | 0.952907 | 0.883 | 0.476933 | 0.1843 | 0/0 |
| A9 no terrain + ramp | 0.818387 | 0.934078 | 0.702695 | 0.525068 | 0.957893 | 0.881867 | 0.4689 | 0.1832 | 0/0 |

## Acceptance Flags

| Candidate | all_10 | easy | hard | B104 ground | support | ground support | topology |
|---|---|---|---|---|---|---|---|
| A4 terrain-normal-only | True | True | True | True | True | True | True |
| A8 no terrain terms | True | True | True | True | True | True | True |
| B2 terrain confidence-gated | True | True | True | True | True | True | True |
| A9 no terrain + ramp | True | False | True | True | True | True | True |

## Interpretation

- A8 has the best all_10 F (`0.828707`) and best easy/control F (`0.952138`) among the compared arms.
- A4 is a near tie in all_10 and is slightly stronger on hard/roof_complex (`0.706229` / `0.538565`), but A8 has much stronger mean ground_cov (`0.984767` vs `0.8844`).
- B2 preserves B104 and has better height error on average (`0.658866`), but it does not beat A8 on all_10/easy and has substantially lower mean ground_cov.
- A9 improves terrain_sensitive F (`0.957893`), but regresses all_10 and easy/control relative to A8.
- All compared completed arms have zero mean open_edges and zero mean non_manifold_edges under Metric-v1.
- B6 height error remains a residual issue and is not solved by A8; it should be tracked in the 4-way pilot.

## Viewer QA

Saved Stage3 preview matrices were created under `phase_s6b_acceptance/viewer_screenshots/`.
- `B104`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B104__candidate_matrix.png`
- `B6`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B6__candidate_matrix.png`
- `B3`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B3__candidate_matrix.png`
- `B123`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B123__candidate_matrix.png`
- `B126`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B126__candidate_matrix.png`
- `B2`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B2__candidate_matrix.png`
- `B0`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B0__candidate_matrix.png`
- `B1`: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase_s6b_acceptance/viewer_screenshots/B1__candidate_matrix.png`

The available logs do not contain per-face rejection reasons. `classwise_support_comparison.csv` therefore records classwise support plus per-face matching coverage where available.

Saved-preview review found no visible B104 GroundSurface collapse or wall-ground closure break for A8. B6 height error and roof-complex low-F cases remain residual risks for the next pilot.

## L_structure 4-way Pilot

Allowed: `yes`.

A controlled Baseline / accepted revised Mutual / Structure-only / revised Mutual+Structure 4-way pilot is allowed, with relation hints M7/M8 still disabled unless separately tested.
