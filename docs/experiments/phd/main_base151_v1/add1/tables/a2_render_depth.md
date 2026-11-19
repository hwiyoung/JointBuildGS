# a2_render_depth

가-2: camera-z depth difference (m) on building pixels, method render (4.2 unit renders) minus campus MVS and minus the prior depth map (OUT/priordepth); negative = the render is nearer to the camera (surface higher for nadir views)

scientific_verdict: null

| run | cell | views | views_available | building_pixels | render_minus_mvs_median | render_minus_mvs_nmad | render_minus_mvs_p10 | render_minus_mvs_p90 | render_minus_prior_median | render_minus_prior_nmad | prior_pixels |
|---|---|---|---|---|---|---|---|---|---|---|---|
| b151_2DGS_s0 | 2 | 20 | 495 | 1401420 | -0.176 | 0.372 | -2.593 | 0.148 | -0.271 | 0.408 | 1400954 |
| b151_2DGS_s0 | 3 | 20 | 306 | 3629196 | -0.339 | 0.417 | -3.780 | 0.010 | -0.359 | 0.433 | 3629196 |
| b151_GeoGS_ALS_s0 | 2 | 20 | 495 | 1406584 | -0.235 | 0.245 | -0.611 | 0.065 | -0.301 | 0.240 | 1406133 |
| b151_GeoGS_ALS_s0 | 3 | 20 | 306 | 3634042 | -0.449 | 0.333 | -0.994 | -0.093 | -0.458 | 0.331 | 3634042 |
| b151_LGDM_ALS | 2 | 20 | 495 | 1404638 | 0.050 | 0.070 | -0.061 | 0.278 | 0.000 | 0.000 | 1404172 |
| b151_LGDM_ALS | 3 | 20 | 306 | 3626625 | 0.025 | 0.065 | -0.062 | 0.220 | 0.000 | 0.000 | 3626625 |
