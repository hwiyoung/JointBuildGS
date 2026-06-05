# FC-S6D Phase 0: A8 Active Terms Inventory

## Scope
Inspection only. No training, Stage3, Metric-v1, L_structure, or G2 run was performed.

## A8 Reference
- Config: `configs/fc_s6/A8_no_terrain_terms.yaml`
- Checkpoint: `results/FC_S6_componentwise_revised_lmutual_design_validation/phase1_existing_terms/runs/A8_no_terrain_terms/ckpt/final.pt`
- `w_mutual`: `0.1`
- `mutual_warmup`: `10000`
- `mutual_schedule`: `constant`
- `mutual_ramp_steps`: `0`
- `mutual_mode`: `full`
- `mutual_tau`: `0.15`
- `mutual_height_th`: `0.15`
- `gravity_file`: `results/phase2_synthesis/gravity.json`

## Actual Active Terms

A8 is a terrain-off reference, but the current config still enables the roof-side height term.
That means A8 is not only wall/roof normal priors; it is wall verticality + roof non-wall + roof-side height.

| term | enabled | formula | target |
|---|---:|---|---|
| `wall_verticality` | True | `mean p_wall * (n dot g)^2` | semantic_faces/WallSurface |
| `roof_nonwall_prior` | True | `mean p_roof * relu(tau - (n dot g)^2)^2` | semantic_faces/RoofSurface |
| `terrain_normal` | False | `mean p_terrain * gate * (1 - abs(n dot g))^2` | semantic_faces/GroundSurface candidate evidence |
| `roof_side_height` | True | `mean p_roof * relu(height_th - height)^2` | shell_diagnostics/height-volume |
| `terrain_side_height` | False | `mean p_terrain * gate * relu(height - terrain_height_ref)^2` | semantic_faces/GroundSurface and shell height |
| `roof_wall_relation_placeholder` | False | `not implemented in train path` | face_graph/roof-wall adjacency |
| `terrain_wall_relation_placeholder` | False | `not implemented in train path` | face_graph/wall-ground adjacency |

## Active/Inactive Summary
- Active: `wall_verticality`, `roof_nonwall_prior`, `roof_side_height`
- Inactive: `terrain_normal`, `terrain_side_height`, `roof_wall_relation_placeholder`, `terrain_wall_relation_placeholder`

## Detach and Directionality
- A8 uses `mutual_mode: full`, so semantic probabilities and geometry both receive gradients.
- `A8_v2_geo` keeps the same active terms but uses `mutual_mode: sem2geo`, detaching `p_wall` and `p_roof`.
- `A8_v2_joint` adds an explicit roof/wall semantic calibration term on top of `A8_v2_geo`.

## Base Loss Components
- Base loss is `w_photo*L_photo + w_depth*L_depth + w_normal*L_normal + w_nc*L_nc + w_distort*L_distort + w_sem*L_sem`.
- `w_structure` is `0.0` in A8 and remains disabled for FC-S6D.
