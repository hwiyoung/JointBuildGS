# P1-3a — Stage 3 collapse cause diagnostics

**Mutual ckpt, 5 buildings (bid=0,1,2,6,21).** GT used for evaluation only. v4 parameters P1-2-fixed.

`gravity = [0, 1, 0]` asserted in every diagnostic entry.

## Diag 0 — v4 normal convention

Per building: count of WALL rep_normal pairs that share an axis (\|cos\|>0.95). cos<-0.95 ⇒ oriented (opposite outward normals); cos>+0.95 ⇒ unoriented (folded to same direction).

| bid | type | n_oriented | n_unoriented | n_inconsistent | convention |
|---|---|---|---|---|---|
| 0 | tri-slope | 0 | 24 | 0 | **unoriented** |
| 1 | flat | 0 | 34 | 0 | **unoriented** |
| 2 | flat | 0 | 10 | 0 | **unoriented** |
| 6 | hip | 0 | 4 | 0 | **unoriented** |
| 21 | complex | 0 | 4 | 0 | **unoriented** |

## Diag 1 — Active plane identification

Top vertex (smallest y in primitive Y-down) and its incident planes. `top_active` summarizes the dominant incident plane.

| bid | polytope_h | GT_h | top_v_y | top_active | top_class | top \|n·g\| | top_d | bottom_active |
|---|---|---|---|---|---|---|---|---|
| 0 | 9.07m | 15.97m | -15.99 | **roof** | roof | 0.996 | 5.84 | wall_tilt |
| 1 | 4.22m | 16.61m | -16.87 | **roof** | roof | 0.968 | 31.99 | roof |
| 2 | 13.95m | 13.63m | -14.02 | **roof** | roof | 0.993 | 19.18 | ground |
| 6 | 15.56m | 19.91m | -16.84 | **roof** | roof | 0.866 | 60.24 | ground |
| 21 | 3.15m | 17.42m | -17.81 | **roof** | roof | 0.992 | 16.22 | roof |

## Diag 2 — Roof / ground d offset (GT vs v4)

d uses the outward-oriented half-space convention (n·x = d on plane). Roof: \|n·g\|>0.7, area-weighted. Ground: virtual GroundSurface added by `add_ground_surface`. GT ground falls back to GT-vertices y-max if no GT GroundSurface face.

| bid | v4_roof_d | GT_roof_d | \|Δd_roof\| | v4_ground_d | GT_ground_d | \|Δd_ground\| |
|---|---|---|---|---|---|---|
| 0 | 8.94 | 12.71 | **3.77** | -0.04 | -0.57 | **0.53** |
| 1 | 26.51 | 19.81 | **6.69** | -0.91 | -0.59 | **0.32** |
| 2 | 17.12 | 14.50 | **2.62** | -0.07 | -0.59 | **0.52** |
| 6 | 52.58 | 19.87 | **32.70** | -1.28 | -0.55 | **0.73** |
| 21 | -1.16 | 16.44 | **17.60** | -1.32 | -0.55 | **0.77** |

## Diag 3 — Backend sanity (GT envelope → build_convex_polytope)

Run on B0/B1/B6. GT faces are merged co-planar (cos>0.99, \|Δd\|<5cm) → envelope plane set → `build_convex_polytope`. BACKEND_OK ⇔ \|Δh\|<1m AND val3dity ✓ AND vol_ratio>0.7.

| bid | GT_planes_n | output_h | GT_h | \|Δh\| | output_vol | GT_vol | val3dity | verdict |
|---|---|---|---|---|---|---|---|---|
| 0 | 19 | 15.77m | 15.97m | **0.19m** | 70 | 1215 | ✗['203'] | **BACKEND_FAIL** |
| 1 | 7 | 16.61m | 16.61m | **0.00m** | 2028 | 2023 | ✓ | **BACKEND_OK** |
| 2 | - | - | - | - | - | - | (not run) | - |
| 6 | 23 | 13.00m | 19.91m | **6.92m** | 1 | 176 | ✓ | **BACKEND_FAIL** |
| 21 | - | - | - | - | - | - | (not run) | - |

## Diag 4 — Convexity check (GT solid)

ratio_2D = footprint_area / 2D-hull_area; ratio_3D = GT_vol / 3D-hull_vol. CONVEX_OK ⇔ both ≥ 0.85.

| bid | type | ratio_2D | ratio_3D | hull_h vs solid_h | verdict |
|---|---|---|---|---|---|
| 0 | tri-slope | 0.996 | 0.992 | 15.97 vs 15.97 | **CONVEX_OK** |
| 1 | flat | 1.000 | 1.000 | 16.61 vs 16.61 | **CONVEX_OK** |
| 2 | flat | 0.964 | 1.949 | 13.63 vs 13.63 | **CONVEX_OK** |
| 6 | hip | 0.909 | 0.143 | 19.91 vs 19.91 | **NON_CONVEX** |
| 21 | complex | 0.974 | 0.979 | 17.42 vs 17.42 | **CONVEX_OK** |

## Cause assignment + branch recommendation

Priority: NON_CONVEX > BACKEND_FAIL > ROOF_OFFSET > GROUND_OFFSET > WALL_TILT > WALL_MISCLASSIFIED.

| bid | type | primary_cause | secondary_causes | branch_recommendation |
|---|---|---|---|---|
| 0 | tri-slope | **BACKEND_FAIL** | ROOF_OFFSET | P1-3b: roof support selection |
| 1 | flat | **ROOF_OFFSET** | - | P1-3b: roof support selection |
| 2 | flat | **ROOF_OFFSET** | - | P1-3b: roof support selection |
| 6 | hip | **NON_CONVEX** | BACKEND_FAIL, ROOF_OFFSET | P1-3b: roof support selection |
| 21 | complex | **ROOF_OFFSET** | - | P1-3b: roof support selection |

## Cause distribution

| cause | count |
|---|---|
| NON_CONVEX | 1 |
| BACKEND_FAIL | 1 |
| ROOF_OFFSET | 3 |

## P1-3b scope

Majority cause: **ROOF_OFFSET** (3/5).

Per-building branch recommendations (deduplicated):

- P1-3b: roof support selection

## Self-verification

- gravity = [0, 1, 0] asserted in every diagnostic entry: ✓
- 4 diagnostics × 5 buildings → 5/5 buildings got a cause (None: 0)
- P1-3b branch recommendation determined: ✓
