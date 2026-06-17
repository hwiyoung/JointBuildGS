# W2-2b City3D Diagnosis

- Run ID: `w2_2b_city3d_diagnosis_20260612_191242`
- Base W2-2 run: `w2_2_city3d_default_20260612_175449`
- Predeclared decision rule: if the ALS coverage-control sample success rate remains below 50% after snap/primitive recheck and 1200s timeout rerun, classify City3D as unsuitable for this scene type and stop further City3D structure work.
- Best single val3dity recheck setting used for the sample decision: `multisurface_snap001`.

## ALS val3dity Error Codes

| code | description | affected buildings | error instances | representatives |
| --- | --- | ---: | ---: | --- |
| `302` | SHELL_NOT_CLOSED | 119 | 573 | `DEBY_LOD2_104583447;DEBY_LOD2_107807336;DEBY_LOD2_108246888;DEBY_LOD2_108247349;DEBY_LOD2_108247350;DEBY_LOD2_108247351` |
| `303` | NON_MANIFOLD_CASE | 27 | 272 | `DEBY_LOD2_108580335;DEBY_LOD2_4906968;DEBY_LOD2_4906969;DEBY_LOD2_4906970;DEBY_LOD2_4906989;DEBY_LOD2_4906998` |
| `307` | POLYGON_WRONG_ORIENTATION | 26 | 164 | `DEBY_LOD2_108580335;DEBY_LOD2_4906969;DEBY_LOD2_4906970;DEBY_LOD2_4906989;DEBY_LOD2_4906998;DEBY_LOD2_4906999` |
| `102` | CONSECUTIVE_POINTS_SAME | 20 | 71 | `DEBY_LOD2_104583794;DEBY_LOD2_107802038;DEBY_LOD2_4907012;DEBY_LOD2_4907018;DEBY_LOD2_4907034;DEBY_LOD2_4907156` |
| `104` | RING_SELF_INTERSECTION | 5 | 9 | `DEBY_LOD2_108250120;DEBY_LOD2_4907031;DEBY_LOD2_4907167;DEBY_LOD2_4907202;DEBY_LOD2_4908050` |

## Representative OBJ Renders

The representative OBJ coordinates remain in EPSG:25832-scale coordinates, not a small local origin. This removes the main local-coordinate suspicion for the invalidity pattern.

| code | building | vertices | faces | X range | Y range | Z range | PNG |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `302` | `DEBY_LOD2_104583447` | 68 | 22 | 690871.710 to 690874.600 | 5336174.330 to 5336178.550 | 514.374 to 532.244 | `docs/figs/w2_2b_valerr_302_DEBY_LOD2_104583447.png` |
| `302` | `DEBY_LOD2_107807336` | 64 | 18 | 690789.880 to 690804.570 | 5336302.600 to 5336332.210 | 513.482 to 519.139 | `docs/figs/w2_2b_valerr_302_DEBY_LOD2_107807336.png` |
| `303` | `DEBY_LOD2_108580335` | 495 | 202 | 691093.740 to 691132.510 | 5336211.380 to 5336257.760 | 512.822 to 533.475 | `docs/figs/w2_2b_valerr_303_DEBY_LOD2_108580335.png` |
| `303` | `DEBY_LOD2_4906968` | 194 | 54 | 690891.410 to 690949.090 | 5336021.120 to 5336138.380 | 509.504 to 539.445 | `docs/figs/w2_2b_valerr_303_DEBY_LOD2_4906968.png` |
| `307` | `DEBY_LOD2_108580335` | 495 | 202 | 691093.740 to 691132.510 | 5336211.380 to 5336257.760 | 512.822 to 533.475 | `docs/figs/w2_2b_valerr_307_DEBY_LOD2_108580335.png` |
| `307` | `DEBY_LOD2_4906969` | 430 | 176 | 690916.690 to 690935.620 | 5336008.570 to 5336025.310 | 515.873 to 530.435 | `docs/figs/w2_2b_valerr_307_DEBY_LOD2_4906969.png` |

## val3dity Snap/Primitive Recheck

| setting | primitive | snap tol | n | valid | invalid | valid rate | top remaining errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `solid_snap001` | Solid | 0.001 | 171 | 0 | 171 | 0.0% | `302:119;303:27;307:26;102:20;104:5` |
| `solid_snap01` | Solid | 0.01 | 171 | 0 | 171 | 0.0% | `102:104;302:57;303:9;307:8;104:2` |
| `composite_snap001` | CompositeSurface | 0.001 | 171 | 0 | 171 | 0.0% | `303:138;307:26;102:20;306:8;104:5` |
| `composite_snap01` | CompositeSurface | 0.01 | 171 | 0 | 171 | 0.0% | `102:104;303:63;307:8;306:3;104:2` |
| `multisurface_snap001` | MultiSurface | 0.001 | 171 | 147 | 24 | 86.0% | `102:20;104:5` |
| `multisurface_snap01` | MultiSurface | 0.01 | 171 | 67 | 104 | 39.2% | `102:104;104:2` |

Interpretation: raising snap tolerance to 0.01 did not make any Solid or CompositeSurface case valid. The only large improvement is under the permissive MultiSurface assumption, which treats the OBJ as a loose surface set rather than a closed LoD2 solid.

## ALS 1200s Sample Rerun

The 20-building sample contains all 13 ALS coverage-control timeout cases, plus 7 high-point-count ALS coverage-control val3dity-invalid fillers.

| population | n | original success | after 1200s default Solid | after 1200s best setting | any valid setting | threshold | recommendation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ALS_coverage_control_sample20 | 20 | 0/20 (0.0%) | 0/20 (0.0%) | 8/20 (40.0%) | 8/20 (40.0%) | 50% | `drop` |

### Sample Detail

| rank | building | original reason | point count | return code | elapsed sec | timeout | faces | default valid | best valid | best success |
| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | --- | --- | --- |
| 1 | `DEBY_LOD2_108580336` | `city3d_timeout` | 89840 | 0 | 1041.887 | False | 575 | False | False | False |
| 2 | `DEBY_LOD2_4907519` | `city3d_timeout` | 72648 | 124 | 1200.195 | True | 0 | False | False | False |
| 3 | `DEBY_LOD2_4959460` | `city3d_timeout` | 67741 | 124 | 1200.262 | True | 0 | False | False | False |
| 4 | `DEBY_LOD2_60042` | `city3d_timeout` | 67374 | 0 | 592.231 | False | 472 | False | True | True |
| 5 | `DEBY_LOD2_4906965` | `city3d_timeout` | 57092 | 124 | 1200.327 | True | 0 | False | False | False |
| 6 | `DEBY_LOD2_4906975` | `city3d_timeout` | 33993 | 0 | 286.969 | False | 401 | False | False | False |
| 7 | `DEBY_LOD2_4906966` | `city3d_timeout` | 29785 | 0 | 528.490 | False | 354 | False | False | False |
| 8 | `DEBY_LOD2_4959326` | `city3d_timeout` | 29689 | 0 | 295.899 | False | 629 | False | False | False |
| 9 | `DEBY_LOD2_4959457` | `city3d_timeout` | 24651 | 124 | 1200.254 | True | 0 | False | False | False |
| 10 | `DEBY_LOD2_4906982` | `city3d_timeout` | 16003 | 0 | 858.701 | False | 830 | False | False | False |
| 11 | `DEBY_LOD2_4959336` | `city3d_timeout` | 11413 | 124 | 1200.206 | True | 0 | False | False | False |
| 12 | `DEBY_LOD2_4907180` | `city3d_timeout` | 6719 | 124 | 1200.229 | True | 0 | False | False | False |
| 13 | `DEBY_LOD2_4907204` | `city3d_timeout` | 4329 | 124 | 1200.256 | True | 0 | False | False | False |
| 14 | `DEBY_LOD2_4906967` | `val3dity_invalid` | 43531 | 0 | 165.004 | False | 293 | False | True | True |
| 15 | `DEBY_LOD2_4906968` | `val3dity_invalid` | 32692 | 0 | 22.076 | False | 54 | False | True | True |
| 16 | `DEBY_LOD2_4906981` | `val3dity_invalid` | 27761 | 0 | 13.457 | False | 185 | False | True | True |
| 17 | `DEBY_LOD2_4959323` | `val3dity_invalid` | 26732 | 0 | 9.214 | False | 110 | False | True | True |
| 18 | `DEBY_LOD2_4906983` | `val3dity_invalid` | 12551 | 0 | 4.529 | False | 21 | False | True | True |
| 19 | `DEBY_LOD2_4959458` | `val3dity_invalid` | 12550 | 0 | 4.491 | False | 104 | False | True | True |
| 20 | `DEBY_LOD2_108580335` | `val3dity_invalid` | 11122 | 0 | 12.337 | False | 202 | False | True | True |

## Recommendation

Drop: City3D is unsuitable for this scene type under the tested default pipeline. The W2-2b scope note is to stop further City3D structure/tuning work for these large complex buildings.
