# G1 Core Table

- Canonical Roofer output: `w3_2b_roofer_repeatability_20260612_220747/run_2`.
- Denominator for the main comparison rows is the W2-1c coverage-control population, 93 buildings, unless the row notes otherwise.

| metric | ALS | DIM | gap | Section 6 threshold position |
| --- | --- | --- | --- | --- |
| LoD2.2 generation rate (assembly) | 92/93 (98.9%) | 85/93 (91.4%) | -7.5 pp | no direct Section 6 threshold; paired assembly table reports exact McNemar p |
| Final success rate | 87/93 (93.5%) | 75/93 (80.6%) | -12.9 pp | no direct Section 6 threshold |
| Plane F1 median | 0.666667 | 0.571429 | -0.095238 (old harness gap: -0.128571) | observed=0.095238; threshold=0.100000; observed-threshold=-0.004762 |
| Exterior boundary Chamfer (m) | 0.126200 | 0.151802 | 0.025602 | observed=1.202868; threshold=1.500000; observed-threshold=-0.297132 |
| Internal boundary Hausdorff (m) | 1.470091 | 1.744066 | 0.273975 | auxiliary metric; no direct Section 6 threshold |
| Height NMAD (m) | 0.059665 | 0.080237 | 0.020572 | no direct Section 6 threshold |
| val3dity valid rate | 88/93 (94.6%) | 83/93 (89.2%) | -5.4 pp | observed=5.376344; threshold=10.000000; observed-threshold=-4.623656 |

Footnote: Plane F1 canonical gap is DIM minus ALS = -0.095238; the pre-canonical W3-1 harness gap was -0.128571.
