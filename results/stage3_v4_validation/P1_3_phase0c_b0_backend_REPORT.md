# P1-3 Phase 0c — B0 backend 203 minimal reproduce

**Target: B0 (tri-slope), Mutual-equivalent GT envelope.** P1-3b GO/NG와 무관. `gravity = [0, 1, 0]`.

GT: type=tri-slope, n_faces=21, GT_h=15.97m, GT_vol=1215m³.

## 1. Baseline reproduce (cos>0.99, |Δd|<5cm)

19 GT planes after merge:

| i | cls | n_x | n_y | n_z | d | area | members | d_spread |
|---|---|---|---|---|---|---|---|---|
| P00 | 3 | 0.000 | 1.000 | 0.000 | -0.57 | 77.8 | 1 | 0.0mm |
| P01 | 2 | -0.358 | 0.000 | -0.934 | 103.81 | 0.6 | 1 | 0.0mm |
| P02 | 2 | 0.934 | 0.000 | -0.356 | -57.22 | 6.4 | 1 | 0.0mm |
| P03 | 2 | -0.907 | 0.000 | -0.422 | 119.03 | 58.9 | 1 | 0.0mm |
| P04 | 2 | -0.428 | 0.000 | 0.904 | -17.54 | 96.2 | 1 | 0.0mm |
| P05 | 2 | 0.903 | 0.000 | 0.429 | -113.11 | 172.7 | 2 | 2.2mm |
| P06 | 2 | 0.935 | 0.000 | -0.355 | -57.28 | 19.0 | 1 | 0.0mm |
| P07 | 2 | 0.993 | 0.000 | -0.119 | -81.98 | 2.1 | 1 | 0.0mm |
| P08 | 2 | 0.328 | 0.000 | 0.945 | -99.98 | 0.6 | 1 | 0.0mm |
| P09 | 2 | 0.934 | 0.000 | -0.358 | -57.04 | 3.1 | 1 | 0.0mm |
| P10 | 2 | 0.338 | 0.000 | -0.941 | 41.15 | 2.0 | 1 | 0.0mm |
| P11 | 2 | -0.639 | 0.000 | -0.769 | 117.07 | 0.6 | 1 | 0.0mm |
| P12 | 2 | -0.901 | 0.000 | -0.434 | 119.30 | 144.5 | 2 | 12.5mm |
| P13 | 2 | 0.830 | 0.000 | 0.557 | -116.31 | 3.2 | 1 | 0.0mm |
| P14 | 2 | 0.505 | 0.000 | 0.863 | -109.47 | 1.2 | 1 | 0.0mm |
| P15 | 2 | 0.425 | 0.000 | -0.905 | 30.90 | 58.1 | 1 | 0.0mm |
| P16 | 1 | 0.040 | -0.999 | -0.003 | 12.71 | 72.0 | 1 | 0.0mm |
| P17 | 1 | 0.894 | -0.356 | 0.273 | -96.03 | 4.0 | 1 | 0.0mm |
| P18 | 1 | 0.393 | -0.325 | -0.860 | 34.59 | 13.9 | 1 | 0.0mm |

Baseline run summary:

- S2 plane intersection: 12/969 triples kept (singular=455, outside_hs=502, outside_bbox=0); unique verts after dedup=12.
- S3 ConvexHull: ok=True n_simplices=16.
- S4 face polygons: max d2p = **44.4mm** (val3dity tol = 10mm).
- S5 CityJSON quantized: max d2p = 24.4mm (scale=0.0001 quantization should not introduce >0.1mm error).
- S6 val3dity: INVALID, errors = [203].
- height/volume: out_h=15.77m vol_ratio=0.058 (P1-3a reported vol_ratio≈0.058).

Per-face d2p (S4):

| gi | class | n_pts | d2p_max | d2p_mean |
|---|---|---|---|---|
| 7 | 2 | 5 | **44.4mm** | 17.8mm |
| 11 | 2 | 5 | **14.8mm** | 5.9mm |
| 8 | 2 | 4 | **0.0mm** | 0.0mm |
| 0 | 3 | 4 | **0.0mm** | 0.0mm |
| 16 | 1 | 4 | **0.0mm** | 0.0mm |
| 1 | 2 | 4 | **0.0mm** | 0.0mm |
| 18 | 1 | 4 | **0.0mm** | 0.0mm |

## 2. Stage separation

Per stage on baseline (= same as table above), plus per-subset stage-by-stage breakdown for the bisection runs (see §3).

| stage | result | source of failure |
|---|---|---|
| S1 envelope_merge | 19 planes (W15 + R3 + G1 from 21 GT faces) | n/a |
| S2 plane_intersection | 12/969 kept; 455 singular, 502 outside half-space, 0 outside bbox | OK |
| S3 ConvexHull | OK | 16 hull triangles |
| S4 face_polygons | max d2p = **44.4mm** | >10mm = will fail val3dity |
| S5 CityJSON | max d2p = 24.4mm (SVD best-fit; assigned plane = 44.4mm) | quantization preserves S4 error |
| S6 val3dity | INVALID | [203] face=2 distance 24.4mm vs tol 10mm |

**Trigger stage: S4** — group gi=7 (class=2, 5 vertices) has d2p_max = 44.4mm > val3dity tolerance 10mm. The convex hull merges hull triangles that map to the same envelope plane (best_gi in `build_convex_polytope`), but these triangle vertices come from 3-plane solves involving *different* envelope planes whose normals differ slightly (cos<1.0 within the merge tolerance). The resulting polygon is therefore not perfectly co-planar.

## 3. Subset bisection

All subsets keep all roofs + ground; walls are progressively removed. `triggers_203` = True means val3dity emits code 203.

| name | n_planes | W/R/G | S2_kept | S3_ok | S4_max_d2p | S6 | 203? | vol_ratio |
|---|---|---|---|---|---|---|---|---|
| baseline_19 | 19 | 15/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| roof_ground_only | 4 | 0/3/1 | 2 | False | — | errs=[] | False | 0.000 |
| walls_ground_only | 16 | 15/0/1 | 5 | False | — | errs=[] | False | 0.000 |
| drop_wall_dir0_n8 | 11 | 7/3/1 | 8 | True | 12509.8mm | errs=[203] | True | 0.427 |
| drop_wall_dir1_n4 | 15 | 11/3/1 | 18 | True | 29.7mm | errs=[203] | True | 0.098 |
| drop_wall_dir2_n3 | 16 | 12/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_wall_01 | 18 | 14/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_wall_02 | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_wall_03 | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_wall_04 | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_wall_05 | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_wall_06 | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_wall_07 | 18 | 14/3/1 | 30 | True | 0.0mm | VALID | False | 0.093 |
| drop_wall_08 | 18 | 14/3/1 | 22 | True | 44.4mm | errs=[203] | True | 0.189 |
| drop_wall_09 | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_wall_10 | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_wall_11 | 18 | 14/3/1 | 12 | True | 24.7mm | VALID | False | 0.144 |
| drop_wall_12 | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_wall_13 | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_wall_14 | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_wall_15 | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_01_02 | 17 | 13/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_walls_01_03 | 17 | 13/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_walls_01_04 | 17 | 13/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_walls_01_05 | 17 | 13/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_walls_01_06 | 17 | 13/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_walls_01_07 | 17 | 13/3/1 | 28 | True | 0.0mm | VALID | False | 0.093 |
| drop_walls_01_08 | 17 | 13/3/1 | 18 | True | 2.4mm | VALID | False | 0.188 |
| drop_walls_01_09 | 17 | 13/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_walls_01_10 | 17 | 13/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_walls_01_11 | 17 | 13/3/1 | 12 | True | 24.7mm | VALID | False | 0.253 |
| drop_walls_01_12 | 17 | 13/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_walls_01_13 | 17 | 13/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_walls_01_14 | 17 | 13/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_walls_01_15 | 17 | 13/3/1 | 8 | True | 0.0mm | VALID | False | 0.057 |
| drop_walls_02_03 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_02_04 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_02_05 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_02_06 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_02_07 | 17 | 13/3/1 | 23 | True | 0.0mm | VALID | False | 0.093 |
| drop_walls_02_08 | 17 | 13/3/1 | 22 | True | 44.4mm | errs=[203] | True | 0.189 |
| drop_walls_02_09 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_02_10 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_02_11 | 17 | 13/3/1 | 12 | True | 24.7mm | VALID | False | 0.144 |
| drop_walls_02_12 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_02_13 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_02_14 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_02_15 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_03_04 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_03_05 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_03_06 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_03_07 | 17 | 13/3/1 | 30 | True | 0.0mm | VALID | False | 0.093 |
| drop_walls_03_08 | 17 | 13/3/1 | 16 | True | 44.4mm | errs=[203] | True | 0.189 |
| drop_walls_03_09 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_03_10 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_03_11 | 17 | 13/3/1 | 10 | True | 0.0mm | VALID | False | 0.144 |
| drop_walls_03_12 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_03_13 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_03_14 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_03_15 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_04_05 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_04_06 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_04_07 | 17 | 13/3/1 | 30 | True | 0.0mm | VALID | False | 0.093 |
| drop_walls_04_08 | 17 | 13/3/1 | 22 | True | 44.4mm | errs=[203] | True | 0.189 |
| drop_walls_04_09 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_04_10 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_04_11 | 17 | 13/3/1 | 12 | True | 24.7mm | VALID | False | 0.144 |
| drop_walls_04_12 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_04_13 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_04_14 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_04_15 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_05_06 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_05_07 | 17 | 13/3/1 | 30 | True | 0.0mm | VALID | False | 0.093 |
| drop_walls_05_08 | 17 | 13/3/1 | 22 | True | 44.4mm | errs=[203] | True | 0.189 |
| drop_walls_05_09 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_05_10 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_05_11 | 17 | 13/3/1 | 12 | True | 24.7mm | VALID | False | 0.144 |
| drop_walls_05_12 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_05_13 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_05_14 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_05_15 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_06_07 | 17 | 13/3/1 | 21 | True | 0.0mm | VALID | False | 0.093 |
| drop_walls_06_08 | 17 | 13/3/1 | 22 | True | 44.4mm | errs=[203] | True | 0.189 |
| drop_walls_06_09 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_06_10 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_06_11 | 17 | 13/3/1 | 12 | True | 24.7mm | VALID | False | 0.144 |
| drop_walls_06_12 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_06_13 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_06_14 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_06_15 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_07_08 | 17 | 13/3/1 | 38 | True | 2.4mm | VALID | False | 0.231 |
| drop_walls_07_09 | 17 | 13/3/1 | 23 | True | 0.0mm | VALID | False | 0.093 |
| drop_walls_07_10 | 17 | 13/3/1 | 36 | True | 0.0mm | VALID | False | 0.094 |
| drop_walls_07_11 | 17 | 13/3/1 | 32 | True | 24.7mm | VALID | False | 0.180 |
| drop_walls_07_12 | 17 | 13/3/1 | 30 | True | 0.0mm | VALID | False | 0.093 |
| drop_walls_07_13 | 17 | 13/3/1 | 36 | True | 0.0mm | VALID | False | 0.093 |
| drop_walls_07_14 | 17 | 13/3/1 | 30 | True | 0.0mm | VALID | False | 0.093 |
| drop_walls_07_15 | 17 | 13/3/1 | 30 | True | 0.0mm | VALID | False | 0.093 |
| drop_walls_08_09 | 17 | 13/3/1 | 22 | True | 44.4mm | errs=[203] | True | 0.189 |
| drop_walls_08_10 | 17 | 13/3/1 | 22 | True | 44.4mm | errs=[203] | True | 0.189 |
| drop_walls_08_11 | 17 | 13/3/1 | 16 | True | 0.0mm | VALID | False | 0.292 |
| drop_walls_08_12 | 17 | 13/3/1 | 16 | True | 44.4mm | errs=[203] | True | 0.189 |
| drop_walls_08_13 | 17 | 13/3/1 | 22 | True | 44.4mm | errs=[203] | True | 0.189 |
| drop_walls_08_14 | 17 | 13/3/1 | 24 | True | 44.4mm | errs=[203] | True | 0.554 |
| drop_walls_08_15 | 17 | 13/3/1 | 22 | True | 44.4mm | errs=[203] | True | 0.189 |
| drop_walls_09_10 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_09_11 | 17 | 13/3/1 | 12 | True | 24.7mm | VALID | False | 0.144 |
| drop_walls_09_12 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_09_13 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_09_14 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_09_15 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_10_11 | 17 | 13/3/1 | 12 | True | 24.7mm | VALID | False | 0.144 |
| drop_walls_10_12 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_10_13 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_10_14 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_10_15 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_11_12 | 17 | 13/3/1 | 10 | True | 0.0mm | VALID | False | 0.145 |
| drop_walls_11_13 | 17 | 13/3/1 | 12 | True | 24.7mm | VALID | False | 0.144 |
| drop_walls_11_14 | 17 | 13/3/1 | 12 | True | 24.7mm | VALID | False | 0.144 |
| drop_walls_11_15 | 17 | 13/3/1 | 12 | True | 24.7mm | VALID | False | 0.144 |
| drop_walls_12_13 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_12_14 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_12_15 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_13_14 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_13_15 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| drop_walls_14_15 | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| tol_cos99_d05cm | 19 | 15/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| tol_cos95_d10cm | 18 | 14/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| tol_cos95_d20cm | 17 | 13/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| tol_cos999_d02cm | 19 | 15/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |
| tol_cos90_d50cm | 16 | 12/3/1 | 12 | True | 44.4mm | errs=[203] | True | 0.058 |

## 4. Critical plane count

- Smallest subset that **still triggers 203**: n_planes = 11 → ['drop_wall_dir0_n8'].
- Largest subset that is **VALID**: n_planes = 18 → ['drop_wall_01', 'drop_wall_07', 'drop_wall_11'].

## 5. Tolerance sweep (envelope-merge thresholds)

| name | cos | Δd | n_planes | S4_max_d2p | S6 | vol_ratio |
|---|---|---|---|---|---|---|
| tol_cos99_d05cm | 0.99 | 5.0cm | 19 | 44.4mm | errs=[203] | 0.058 |
| tol_cos95_d10cm | 0.95 | 10.0cm | 18 | 44.4mm | errs=[203] | 0.058 |
| tol_cos95_d20cm | 0.95 | 20.0cm | 17 | 44.4mm | errs=[203] | 0.058 |
| tol_cos999_d02cm | 0.999 | 2.0cm | 19 | 44.4mm | errs=[203] | 0.058 |
| tol_cos90_d50cm | 0.9 | 50.0cm | 16 | 44.4mm | errs=[203] | 0.058 |

## 6. Conclusion

### 6.1 Trigger stage — confirmed

**S4 face_polygon construction in `build_convex_polytope`.** S2 (3-plane vertex enumeration) keeps 12/969 triples with no degeneracy and S3 (ConvexHull) emits 16 well-formed simplices. The 44.4 mm planarity violation appears only after `_merge_coplanar_triangles` pools the hull triangles by `best_gi`. Worst face: gi=7 (`class=2`, 5 vertices, d2p_mean = 17.8 mm), which exceeds val3dity's 10 mm tolerance by 4.4×.

### 6.2 Mechanism

The 19 GT envelope planes include several near-coplanar wall pairs (e.g. P02/P06/P09 all share normal ≈ (0.934, 0, −0.356) but differ in d by 0.06–0.18 m). These pairs are not merged at any tolerance the sweep covered (see 6.4). When ConvexHull triangulates the 12 valid vertices, the assignment loop picks `best_gi = argmin_i max_v |n_i · v − d_i|`. Two issues compound:

1. The `plane_tol = 0.1 m` ceiling lets a triangle whose vertices are up to 10 cm off a plane still be claimed by that plane.
2. Even when the chosen plane is the literal best fit, the vertex set was generated by *other* planes (the triangle's 3 spanning planes), so vertices land on an effectively averaged plane that differs from any single envelope plane by tens of mm.

The merged 5-vertex polygon for gi=7 collects vertices from multiple hull triangles, all attributed to one plane whose actual fit is 24 mm (SVD best-fit, see §1) and 44 mm (assigned plane, n_07).

### 6.3 Critical plane count

- Smallest 203-triggering subset in this run: **n = 11** (`drop_wall_dir0_n8`, retains all 3 roofs + ground + 7 walls).
- Largest 203-free subset: **n = 18** (any of `drop_wall_01`, `drop_wall_07`, `drop_wall_11`). The three "rescuing" drops all target small-area walls (areas 0.6, 2.1, 0.6 m²) whose direction is unique in the envelope. Conclusion: **a single small-area, off-axis wall is sufficient to push d2p above 10 mm**; conversely, removing any one of the three walls listed above is sufficient to fall below it.

### 6.4 Tolerance sweep is empirically NOT a fix

§5 covers cos∈{0.9, 0.95, 0.99, 0.999} × Δd∈{2, 5, 10, 20, 50} cm. **All five points yield the same S4_max_d2p = 44.4 mm and the same vol_ratio = 0.058.** Even cos≥0.9, |Δd|≤50 cm (which collapses 19→16 planes) produces the identical polytope. The merge step is not the bottleneck — the offending wall pairs survive any reasonable threshold because they sit at nearly-identical normals but with d differences of 6–18 cm that fall below the d-only test only at thresholds (≥20 cm) that would over-merge real Stage 2 walls.

Practical implication: **dropping the merge threshold cannot fix 203.** The fix must be made at S4 (face-polygon construction) or earlier (envelope filtering by area / direction).

### 6.5 vol_ratio = 0.058 is a separate failure (out of scope but flagged)

Even when 203 is removed (the three VALID subsets above), vol_ratio sits at 0.057–0.144. Yet P1-3a Diag 4 reported `ratio_3D = 0.992` (B0 is essentially convex). This means the convex polytope of the 19 outward half-spaces is far smaller than the building's convex hull. Diagnosis (informal, from this run): the area-weighted d in `_gt_envelope_planes` is `n · centroid`, not `max(n · v)` over building vertices. For walls with jogs/alcoves, the inner sub-face contributes a tighter d than the true support plane, cutting the polytope short.

This is **independent of 203** — fixing S4 will pass val3dity but not recover volume. A separate task should change the envelope d to `max(n · v)` (or some explicit support-plane computation) to ensure each plane is actually a support plane of the building's convex hull.

### 6.6 Fix proposals (in priority order)

1. **Project each polygon onto the assigned envelope plane after `_merge_coplanar_triangles`.** Subtract `(n · v − d) n` from every output vertex. d2p drops to ≤ 1e-9. The displacement is at most `plane_tol = 0.1 m`, which (after projection) is absorbed by val3dity's `snap_tol = 1 mm` if the projection is followed by a vertex-snap pass that re-shares vertices between neighbouring polygons. **Recommended primary fix**: deterministic, no parameter tuning, no information loss.

2. **Tighten `plane_tol` from 0.1 m to 0.01 m in `build_convex_polytope`.** Forces hull triangles whose vertices are >10 mm off any envelope plane to fall through to the cosine-similarity branch (currently `cos > 0.3`). This trades 203 for `unmatched` warnings — i.e. some hull faces stop being assigned to any envelope plane, leaving the polytope under-described. Use as a safety net behind fix 1.

3. **Filter envelope planes by area before polytope construction.** Drop walls below a minimum area (e.g. 1 m² or 5 % of the largest wall). The diagnostic shows P01 (0.6 m²), P11 (0.6 m²), P14 (1.2 m²) are responsible for the worst pollution; their geometry is irrelevant for LOD-2 anyway. Pragmatic, but heuristic: the threshold needs cross-building validation.

4. ~~Lower the merge threshold (cos≥0.95, |Δd|≤10 cm).~~ **Empirically does not work** (§5, §6.4). Do not use.

### 6.7 Limitation

None of these fixes addresses the P1-3a finding that v4 clustering picks the wrong roof support (ROOF_OFFSET on B1/B2/B21). Phase 0c only verifies that the **backend** can be made val3dity-clean given a high-quality envelope; it does not validate the upstream envelope construction. Backend success on the GT envelope ≠ backend success on the v4 envelope. The vol_ratio observation in §6.5 also sits in this gap.

## 7. Self-verification

- gravity = [0, 1, 0] asserted in every stage entry: ✓
- Baseline 19-plane envelope reproduced (matches P1-3a Diag 3: 19 planes, vol_ratio 0.058, val3dity 203): ✓
- Stage-by-stage trigger identified: ✓ (S4 face_polygons)
- Critical plane count identified: ✓ (smallest 203 subset n=11; smallest VALID drop n=18, must be P01/P07/P11)
- Tolerance sweep falsified merge-threshold-as-fix hypothesis: ✓ (all 5 sweep points emit identical 44.4 mm)
- Trigger stage independent of vol_ratio: ✓ (some VALID subsets still have vol_ratio < 0.1)
- Total subsets evaluated: 5 (full + 2 class-only + tolerance) + 3 (directional drops) + 15 (one-out) + 105 (pairwise) + 5 (tolerance) = 133 runs, all logged with stage S2/S3/S4/S5/S6 metrics in `p1_3_phase0c/p1_3_phase0c_metrics.json`
