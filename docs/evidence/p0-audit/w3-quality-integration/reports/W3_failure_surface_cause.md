# W3 Failure Surface Cause (T9)

- Run ID: t9_failure_surface_cause_20260615_204200
- Run directory: runs/t9_failure_surface_cause_20260615_204200
- Canonical input: `w3_2b_roofer_repeatability_20260612_220747/run_2`
- Building metrics CSV: `docs/W3_failure_surface_cause_building_metrics.csv`
- Threshold CSV: `docs/W3_failure_surface_cause_thresholds.csv`
- Control summary CSV: `docs/W3_failure_surface_cause_control_summary.csv`
- Metrics JSON: `data/work/diagnose/t9_failure_surface_cause_metrics.json`
- Inputs: failure 8 IDs/T7 output, original UAV images, T2 COLMAP poses, T5 footprint GPKG, T3 DIM density via T7, and ALS LAZ roof reference.
- CRS: EPSG:25832 numeric UTM32 for footprints, ALS, and camera centers after T2 scene-reference transform.
- Scope: automatic cause classification/observation only. P0 acceptance/rejection remains outside this T9 output.

## Failure Surface Cause Table

| building_id | near_nadir_view_count | oblique_view_count | near_nadir_texture_gradient_mean | near_nadir_texture_gradient_p10 | near_nadir_gray_std | near_nadir_brightness_median | near_nadir_shadow_ratio | dim_density_pts_m2 | surface_cause_classification | surface_cause_recoverable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DEBY_LOD2_42364609 | 9 | 281 | 0.02555 | 0.01210 | 0.14255 | 0.675 | 0.005 | 3.892 | 무텍스처 | yes |
| DEBY_LOD2_42364659 | 3 | 222 | 0.02375 | 0.02290 | 0.20518 | 0.765 | 0.032 | 48.576 | 나디르_커버리지부족 | no |
| DEBY_LOD2_42364663 | 15 | 381 | 0.04425 | 0.02639 | 0.15716 | 0.431 | 0.235 | 4057.681 | 구조화부족 | no |
| DEBY_LOD2_4907182 | 33 | 258 | 0.02793 | 0.00701 | 0.16824 | 0.471 | 0.048 | 2.558 | 무텍스처 | yes |
| DEBY_LOD2_4907510 | 7 | 250 | 0.04993 | 0.04382 | 0.14979 | 0.365 | 0.089 | 26.725 | 무텍스처 | yes |
| DEBY_LOD2_4908050 | 4 | 266 | 0.02705 | 0.02360 | 0.13425 | 0.424 | 0.030 | 0.585 | 무텍스처 | yes |
| DEBY_LOD2_4908166 | 4 | 277 | 0.02469 | 0.01490 | 0.13807 | 0.471 | 0.047 | 2.063 | 무텍스처 | yes |
| DEBY_LOD2_4908176 | 9 | 303 | 0.03656 | 0.03315 | 0.22904 | 0.349 | 0.183 | 8.310 | 무텍스처 | yes |

## Adopted Thresholds

| threshold | value | source | interpretation |
| --- | --- | --- | --- |
| near_nadir_incidence_max_deg | 20.000 | fixed T9 definition | view is near-nadir when incidence angle is <= threshold |
| near_nadir_view_count_min | 4.000 | max(3, control_success_71 near-nadir count p10) | nadir coverage is sufficient when count is >= threshold |
| texture_gradient_low_max | 0.02137 | control_success_71 near-nadir roof crop gradient p10 | texture is low when gradient is <= threshold |
| texture_gray_std_low_max | 0.14441 | control_success_71 near-nadir roof crop gray std p25 | texture confirmation uses std <= threshold with low gradient |
| brightness_shadow_low_max | 0.284 | control_success_71 near-nadir roof crop brightness p10 | shadow candidate when brightness is <= threshold |
| shadow_ratio_high_min | 0.286 | max(0.25, control_success_71 near-nadir shadow ratio p90) | shadow candidate when dark-pixel ratio is >= threshold |

## Control Summary

| metric | n | median | p10 | p25 | p75 | p90 |
| --- | --- | --- | --- | --- | --- | --- |
| near-nadir view count | 71 | 12.000 | 4.000 | 8.000 | 23.000 | 28.000 |
| oblique view count | 71 | 273.000 | 172.000 | 209.000 | 345.500 | 368.000 |
| near-nadir gradient mean | 69 | 0.02728 | 0.02137 | 0.02422 | 0.03663 | 0.04381 |
| near-nadir gray std | 69 | 0.18985 | 0.12543 | 0.14441 | 0.21116 | 0.23244 |
| near-nadir brightness | 69 | 0.410 | 0.284 | 0.349 | 0.471 | 0.563 |
| near-nadir shadow ratio | 69 | 0.090 | 0.022 | 0.041 | 0.145 | 0.286 |

## Figure

![texture crop examples](../../../docs/evidence/p0_g1_20260613/figs/fig_13_t9_failure_texture_crops.png)

## Observations

- Surface-cause recovery candidates: 6/8 무텍스처=복구가능 관찰, 2/8 커버리지/그림자/구조화부족 관찰.
- Classification counts: 무텍스처 6, 그림자 0, 나디르_커버리지부족 1, 구조화부족 1.
- 무텍스처 6건 중 3건은 near-nadir 저구배/저분산 threshold-confirmed, 3건은 커버리지·그림자·구조화 trigger가 없는 texture-limited 잔여 관찰이다.
- T7 occlusion was not reused as a cause label here; T9 uses projected roof image texture/lighting and near-nadir view counts.
- Shadow ratio is the fraction of roof-crop grayscale pixels below 0.20; texture is mean grayscale gradient in the projected roof mask.
- `surface_cause_recoverable=yes` marks texture-limited cases as GS-JSO surface-formation candidates for E5 confirmation, not as a P0 decision.
- E5 confirmation is still required before using these T9 categories as a method-level conclusion.
