# FC-S6 Action Decision

## 1. Decision Label

Selected label: `D2_TERRAIN_OFF_IS_BEST`.

A8/M5 reproduced and no completed gated/robust/ramp terrain variant surpassed the terrain-off reference.

This report is triage-only. It does not claim a final revised `L_mutual` unless `D5_REVISED_MUTUAL_READY_FOR_STRUCTURE` is selected.

## 2. Evidence

- A0 baseline all_10 mean F: `0.820763`.
- A1 original mutual all_10 mean F: `0.806918`.
- A4 terrain-normal-only all_10 mean F: `0.828087`.
- Completed priority arms: `6`.
- Priority arm summary:
- `A8_no_terrain_terms`: status=`COMPLETED`, all_10_F=`0.828707`, easy_F=`0.952138`, hard_F=`0.705276`, B104_ground_cov=`1`, B104_ground_support_cov=`0.537`, support_cov=`0.467`, ground_support_cov=`0.1723`, open_edges=`0`, non_manifold_edges=`0`.
- `A6_no_terrain_normal`: status=`COMPLETED`, all_10_F=`0.818219`, easy_F=`0.94723`, hard_F=`0.689207`, B104_ground_cov=`1`, B104_ground_support_cov=`0.517`, support_cov=`0.479533`, ground_support_cov=`0.183`, open_edges=`0`, non_manifold_edges=`0`.
- `A7_no_terrain_height_side`: status=`COMPLETED`, all_10_F=`0.80622`, easy_F=`0.952628`, hard_F=`0.659813`, B104_ground_cov=`0`, B104_ground_support_cov=`0.181`, support_cov=`0.4682`, ground_support_cov=`0.1496`, open_edges=`0`, non_manifold_edges=`0`.
- `B4_terrain_quantile_height`: status=`COMPLETED`, all_10_F=`0.819954`, easy_F=`0.94329`, hard_F=`0.696618`, B104_ground_cov=`1`, B104_ground_support_cov=`0.482`, support_cov=`0.470367`, ground_support_cov=`0.178`, open_edges=`0`, non_manifold_edges=`0`.
- `B2_terrain_confidence_gated`: status=`COMPLETED`, all_10_F=`0.822267`, easy_F=`0.944122`, hard_F=`0.700411`, B104_ground_cov=`1`, B104_ground_support_cov=`0.523`, support_cov=`0.476933`, ground_support_cov=`0.1843`, open_edges=`0`, non_manifold_edges=`0`.
- `A9_no_terrain_terms_ramp`: status=`COMPLETED`, all_10_F=`0.818387`, easy_F=`0.934078`, hard_F=`0.702695`, B104_ground_cov=`1`, B104_ground_support_cov=`0.505`, support_cov=`0.4689`, ground_support_cov=`0.1832`, open_edges=`0`, non_manifold_edges=`0`.

## 3. Cancelled Or Deprioritized Arms

- Cancelled now: `A5_height_relation_only` was interrupted at triage switch because it is lower priority than A8/A6/A7.
- Deprioritized until after terrain-first triage: `A5_height_relation_only`, `B1_terrain_low_weight`, `B3_terrain_class_mass_gated`, `B5_split_height_low_terrain_side`, `B6_terrain_confidence_gated_ramp`.
- Deferred: all Phase 3, all Phase 4, relation hints M7/M8, `L_structure`, and G2.

## 4. Next Concrete Experiment

Adopt `A8_no_terrain_terms` as the terrain-off Mutual candidate for triage follow-up.

Next action: run support/topology/viewer QA for `A8_no_terrain_terms` against Baseline, Original Mutual, M3, M5, and M10. Keep terrain relation hints M7/M8 disabled.

Do not start Phase 3/Phase 4 expansion or `L_structure` until this candidate passes the full acceptance gates.

## 5. Is L_structure Allowed To Start?

No.

`L_structure` is blocked because this report did not select `D5_REVISED_MUTUAL_READY_FOR_STRUCTURE`. Starting `L_structure` now would mix an unresolved `L_mutual` design with a new structural loss and obscure whether terrain/read-out regressions are from Mutual or Structure.
