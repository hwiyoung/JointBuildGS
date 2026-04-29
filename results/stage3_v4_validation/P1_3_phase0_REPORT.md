# P1-3 Phase 0 — prereq diagnostics (0a + 0b + 0d)

**Mutual ckpt, bid=0,1,2,6,21.** GT for evaluation only. v4 parameters P1-2-fixed.

`gravity = [0, 1, 0]` asserted in every diagnostic entry.

Phase 0c (manual trace) is run separately.

## Phase 0a — Diag 4 ratio_3D fix

**Bug**: P1-3a used `vp.mean(axis=0)` as face centroid in the divergence formula `V = (1/3) Σ A·(n·c)`, which is incorrect for non-rectangular planar polygons (vertex mean ≠ true area-weighted centroid). For B2 this produced ratio_3D = 1.949 (impossible: convex hull contains the solid, so ratio ≤ 1).

**Fix**: switch to fan triangulation + signed tetrahedra. Each face is fan-triangulated from v[0]; each triangle (v0, vi, vi+1) contributes `(1/6) · v0 · (v1 × v2)` to the signed volume. Vertices are reversed if the face normal (Newell) is inward, ensuring CCW-outward winding.

| bid | type | old ratio_3D | new ratio_3D | old ratio_2D | new ratio_2D | new verdict |
|---|---|---|---|---|---|---|
| 0 | tri-slope | 0.992 | **0.992** | 0.996 | 0.996 | **CONVEX_OK** |
| 1 | flat | 1.000 | **1.000** | 1.000 | 1.000 | **CONVEX_OK** |
| 2 | flat | 1.949 | **0.968** | 0.964 | 0.964 | **CONVEX_OK** |
| 6 | hip | 0.143 | **0.859** | 0.909 | 0.909 | **CONVEX_OK** |
| 21 | complex | 0.979 | **0.988** | 0.974 | 0.974 | **CONVEX_OK** |

- Phase 0a verdict: 5/5 ratio_3D ≤ 1: **OK** (5/5)
- 5/5 ratio_2D ≤ 1: **OK** (5/5)
- B6 new ratio_3D = 0.859 → **CONVEX_OK**

## Phase 0b — Roof primitive y-distribution

Per building, identify the v4 roof group with the largest weight contribution to the area-weighted v4_roof_d, and classify the failure mode:

- `SPURIOUS_ROOF`: top group has > 30% primitives outside GT roof y-range (Stage 2 sem-head misclassification — out of P1-3b scope).
- `WEIGHT_BUG`: top group dominates the mean (>70%) AND has below-median area — a small outlier biases the mean.
- `SLOPE_D_ARTIFACT`: predicted_y_at_centroid is in the GT roof y-range AND \|Δd\| ≥ 1m (sloped roof; the d-comparison metric is just inappropriate, selection is OK).
- `SELECTION`: \|Δd\| ≥ 1m and none of the above apply.
- `OK`: \|Δd\| < 1m.

| bid | n_horiz_roof_groups | top_gid | top_y_mean | top_area | weight_contrib | GT_roof_y_range | spurious% | predicted_y@centroid | GT_roof_d | v4_roof_d | \|Δd\| | dominant_cause |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2 | 16 | -16.23 | 249.69 | 60.5% | [-16.54, -12.68] | 0.0% | -16.09 | 12.71 | 8.94 | **3.77** | **SLOPE_D_ARTIFACT** |
| 1 | 3 | 8 | -16.71 | 718.80 | 69.2% | [-17.20, -16.94] | 18.4% | -16.51 | 19.81 | 26.66 | **6.84** | **SLOPE_D_ARTIFACT** |
| 2 | 2 | 4 | -14.00 | 322.68 | 63.6% | [-14.23, -13.92] | 0.3% | -13.96 | 14.50 | 17.12 | **2.62** | **SLOPE_D_ARTIFACT** |
| 6 | 3 | 4 | -15.63 | 154.35 | 83.5% | [-20.46, -13.55] | 0.0% | -16.48 | 19.87 | 52.58 | **32.70** | **SLOPE_D_ARTIFACT** |
| 21 | 3 | 3 | -16.77 | 83.80 | 52.1% | [-17.97, -13.95] | 0.6% | -14.04 | 16.44 | 16.47 | **0.03** | **OK** |

## Phase 0d — Centroid-inside orientation prereq

Apply canonical orientation to RAW v4 planes (rep_n, rep_off) BEFORE process_building's `orient_normals_outward`. Centroid is the 10%-trimmed mean of building primitive centres (robust to outliers). For each plane, flip if `n · centroid > d` (centroid is outside the half-space). `inside_ratio` is the fraction of primitive centres satisfying `n·c < d`.

| bid | n_planes | n_walls | n_roofs | mean inside (before) | mean inside (after) | n_planes ratio<0.85 (after) | n_walls_flipped |
|---|---|---|---|---|---|---|---|
| 0 | 24 | 11 | 13 | 0.484 | 0.772 | 15 | 4 |
| 1 | 22 | 15 | 7 | 0.530 | 0.761 | 16 | 7 |
| 2 | 10 | 5 | 5 | 0.571 | 0.744 | 8 | 2 |
| 6 | 10 | 5 | 5 | 0.342 | 0.715 | 9 | 5 |
| 21 | 16 | 5 | 11 | 0.527 | 0.696 | 13 | 1 |

## P1-3b clean case decision

**clean_cases = [1, 2, 6, 21]** (length 4).

Excluded:
- B0: B0 backend-fragile (parallel with Phase 0c)

P1-3b 진행 가능.

## Self-verification

- gravity = [0, 1, 0] asserted in every entry: ✓
- Phase 0a 5건물 ratio_3D ≤ 1: ✓
- Phase 0b 5건물 dominant_cause 할당: ✓
- Phase 0d before/after 표 출력: ✓
- P1-3b clean_cases 결정: ✓ ([1, 2, 6, 21])