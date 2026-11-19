# a2b_expected_vs_median

가-2 check: whole cell model rendered at the same 20 views per cell; camera-z depth minus campus MVS on building pixels for the expected depth (depth_ratio 0, the mesh rule) and the median depth (depth_ratio 1); alpha of the pixels

scientific_verdict: null

| run | cell | status | views | building_pixels | expected_minus_mvs_median | expected_minus_mvs_nmad | median_minus_mvs_median | median_minus_mvs_nmad | median_minus_expected_median | alpha_median | alpha_p10 | alpha_lt_099_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| b151_2DGS_s0 | 2 | 있음 | 20 | 4231370 | -0.239 | 0.486 | -0.202 | 0.482 | 0.003 | 1.000 | 0.999 | 1.415 |
| b151_2DGS_s0 | 3 | 있음 | 20 | 5549438 | -0.398 | 0.511 | -0.334 | 0.539 | -0.001 | 1.000 | 0.997 | 4.273 |
| b151_GeoGS_ALS_s0 | 2 | 있음 | 20 | 4231370 | -0.182 | 0.256 | -0.090 | 0.231 | 0.045 | 1.000 | 0.999 | 2.423 |
| b151_GeoGS_ALS_s0 | 3 | 있음 | 20 | 5549438 | -0.444 | 0.432 | -0.200 | 0.341 | 0.120 | 1.000 | 0.997 | 4.513 |
