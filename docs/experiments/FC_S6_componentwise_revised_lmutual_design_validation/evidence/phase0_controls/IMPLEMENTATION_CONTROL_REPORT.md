# FC-S6 Implementation Control Report

## Scope

- Changed only Stage2 `L_mutual` controls/logging and FC-S6 experiment scaffolding.
- Did not implement `L_structure`.
- Did not start G2.
- Did not modify Stage3Algo-v1 or Metric-v1.
- Did not change footprint/domain assumptions, gravity, source definitions, or the 10-bid building set.
- Stage2 terrain terms refer to primitive-level terrain evidence; `GroundSurface` remains a Stage3 final semantic face.
- GT roof type, GT roof partition, GT final mesh, and GT semantic surfaces are not used to construct Stage2-derived outputs.

## Controls Added

- Existing component enables: `mutual_enable_wall_vertical`, `mutual_enable_roof_nonwall`, `mutual_enable_terrain_normal`, `mutual_enable_height_roof_side`, `mutual_enable_height_terrain_side`.
- Existing component weights: `mutual_w_wall_vertical`, `mutual_w_roof_nonwall`, `mutual_w_terrain_normal`, `mutual_w_height_roof`, `mutual_w_height_terrain`.
- Terrain-safe diagnostic gates: `mutual_terrain_gate_mode` in `none`, `confidence`, `class_mass`, `mass_entropy`; default is `none`.
- Terrain robust height diagnostic: `mutual_terrain_height_reference=terrain_quantile`; default is `fixed`.
- Gradient diagnostics remain interval-controlled by `mutual_grad_audit_every`; no extra autograd calls run when it is `0`.

## Default Behavior

Default-off/default-on equivalence status: `PASS`. See `default_off_equivalence.md`.
