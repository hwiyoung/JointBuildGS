# W attr-outcome regression v1

> 재구성/재학습 없음. 이미지-투영 불사용. 판정 없이 수치와 관찰만 기록한다. CRS는 EPSG:25832.

## 스코프

본 회귀의 주판 = 원래 점군(= §1.5 v1.13의 주 트랙이자 P0 canonical을 낳은 바로 그 점군 — 재료→결과 짝이 인과적으로 정합). GS 점군은 빈7 확정 후 동일 잣대로 측정 (본 비교 실험), 공용 점군화 ablation은 그때 병기, 확증은 E5.

## 결과 런 지문

| 항목 | 경로 | sha256 |
|---|---|---|
| status_csv | `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv` | `4412ee47f8665e1a12663629dd66f9c9612f2e9adca54be38c188f2bc521a9b6` |
| w2_config | `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/config.yaml` | `65a8435b8e95b5cbeb86d3a2b82a8fed0b07e62737dc7714062a4151eb24bdd3` |
| w2_versions | `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/versions.txt` | `4a786bdc66cc29732b208b665c5133aa57af848ff38da8e347d77dc001b9c113` |
| w3_repeatability_versions | `phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/versions.txt` | `0071622cde70adc2a4a62e106468fc7d98d59fc6d5587276db7bbe662caf9c82` |
| w3_run2_als_status | `phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/als_default.csv` | `43ad02e993ac250516d7ce75ffb7539276a1f2e7e4e3449cd461e0646f06d613` |
| w3_run2_dim_status | `phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/dim_default.csv` | `625d49898c140c6d1ecf2dc66196b46a962770a240124049ea9b9493fe826ce1` |
| w3_repeatability_building_status | `phases/p0-audit/docs/W3_2b_roofer_repeatability_building_status.csv` | `6a3ca7d8a13407ba0b7ac34cb1d682ccc66aada10adef988a5b4e7d58521c520` |

Roofer 1.0.0 · val3dity 2.6.0 · plane_detect_epsilon=0.3 · plane_detect_min_points=15 · complexity_factor=0.888. 결과 변수 4종은 Roofer 내부 산출이다. 외부 참조·높이 상수·이미지 투영과 절연(datum-free, attr-v1.1 [E] 확인).

## 입력·결측 규약

- attr 입력: `docs/pointcloud_attributes_v1_2.csv`.
- 결과 정본 런: w2_1. DIM·LiDAR는 각 199동 전수. ACMP는 `gen_8way` 64동 보조 대장.
- 조립 성공 변수는 status CSV의 `has_lod22`를 썼다. 이는 §3.2의 `roofer_ok·roof_surfaces>0` 정의를 W2 status에서 건물 단위로 저장한 열이다.
- no_points 행은 회귀 입력에서 밀도 0·커버리지 0으로 재코딩했다. 노이즈·M3C2·부유·라벨 미정의는 결측 유지, 모델별 complete-case n을 표에 기록했다.
- 로버스트 제외 목록: 42364663, 42364667, 104586480. attr의 ref_invalid 플래그는 참고 열로 유지했다.
- 라벨 축 주지표는 `label_proxy_frac_all`; `label_proxy_frac_ground`는 감도 재추정에만 썼다.

입력 커버리지:

| arm | source | rows |
|---|---|---:|
| raw_acmp | gen_8way_raw_acmp | 64 |
| raw_dense | w2_1 | 199 |
| raw_lidar | w2_1 | 199 |

결과 변수별 사용 가능 행:

| arm | outcome | n |
| --- | --- | --- |
| raw_dense | assembled | 199 |
| raw_dense | val3dity_valid | 179 |
| raw_dense | rf_rmse_lod22 | 131 |
| raw_dense | rf_roof_planes | 179 |
| raw_lidar | assembled | 199 |
| raw_lidar | val3dity_valid | 179 |
| raw_lidar | rf_rmse_lod22 | 178 |
| raw_lidar | rf_roof_planes | 178 |
| raw_acmp | assembled | 64 |
| raw_acmp | val3dity_valid | 64 |
| raw_acmp | rf_rmse_lod22 | 37 |
| raw_acmp | rf_roof_planes | 64 |

## 기술 통계

| arm | axis | n | missing | median | IQR | nonzero_n | nonzero_rate |
|---|---|---:|---:|---:|---|---:|---:|
| raw_dense | pt_density_m2_reg | 199 | 0 | 30.7686 | 0.1764-244.2 | 151 | 0.759 |
| raw_dense | coverage_frac_reg | 199 | 0 | 0.6857 | 0.0267-1 | 151 | 0.759 |
| raw_dense | local_plane_rms_m | 144 | 55 | 0.1517 | 0.1163-0.183 | 144 | 1.000 |
| raw_dense | floater_frac | 151 | 48 | 0.0030 | 0-0.02985 | 93 | 0.616 |
| raw_dense | label_proxy_frac_all | 151 | 48 | 0.0000 | 0-0.1483 | 56 | 0.371 |
| raw_dense | m3c2_rms_m | 143 | 56 | 0.3410 | 0.1723-0.5796 | 143 | 1.000 |
| raw_dense | label_proxy_frac_ground | 140 | 59 | 0.0000 | 0-0.9405 | 56 | 0.400 |
| raw_lidar | pt_density_m2_reg | 199 | 0 | 18.5787 | 16.05-19.85 | 199 | 1.000 |
| raw_lidar | coverage_frac_reg | 199 | 0 | 0.9979 | 0.9932-1 | 199 | 1.000 |
| raw_lidar | local_plane_rms_m | 198 | 1 | 0.1498 | 0.1221-0.1686 | 198 | 1.000 |
| raw_lidar | floater_frac | 199 | 0 | 0.0010 | 0-0.01831 | 115 | 0.578 |
| raw_lidar | label_proxy_frac_all | 199 | 0 | 0.0000 | 0-0 | 22 | 0.111 |
| raw_lidar | m3c2_rms_m | 0 | 199 | none | None | 0 | none |
| raw_lidar | label_proxy_frac_ground | 146 | 53 | 0.0000 | 0-0 | 22 | 0.151 |
| raw_acmp | pt_density_m2_reg | 64 | 0 | 1.2312 | 0.2874-10.35 | 63 | 0.984 |
| raw_acmp | coverage_frac_reg | 64 | 0 | 0.1814 | 0.05793-0.5577 | 63 | 0.984 |
| raw_acmp | local_plane_rms_m | 26 | 38 | 0.1297 | 0.06815-0.1697 | 26 | 1.000 |
| raw_acmp | floater_frac | 63 | 1 | 0.3349 | 0.004768-1 | 60 | 0.952 |
| raw_acmp | label_proxy_frac_all | 63 | 1 | 0.0524 | 3.2e-05-0.1915 | 47 | 0.746 |
| raw_acmp | m3c2_rms_m | 31 | 33 | 2.1325 | 1.12-6.779 | 31 | 1.000 |
| raw_acmp | label_proxy_frac_ground | 57 | 7 | 0.3327 | 0.003195-1 | 47 | 0.825 |

## 다중공선성 점검

밀도↔커버리지 상관:

| arm | n | Pearson r | Spearman rho |
|---|---:|---:|---:|
| raw_dense | 199 | 0.585 | 0.939 |
| raw_lidar | 199 | 0.379 | 0.390 |
| raw_acmp | 64 | 0.626 | 0.949 |

VIF:

| arm | predictor | n | VIF |
|---|---|---:|---:|
| raw_dense | pt_density_m2_reg | 144 | 1.44 |
| raw_dense | coverage_frac_reg | 144 | 1.46 |
| raw_dense | local_plane_rms_m | 144 | 1.22 |
| raw_dense | floater_frac | 144 | 1.10 |
| raw_dense | label_proxy_frac_all | 144 | 1.23 |
| raw_lidar | pt_density_m2_reg | 198 | 1.34 |
| raw_lidar | coverage_frac_reg | 198 | 1.09 |
| raw_lidar | local_plane_rms_m | 198 | 1.35 |
| raw_lidar | floater_frac | 198 | 1.11 |
| raw_lidar | label_proxy_frac_all | 198 | 1.02 |
| raw_acmp | pt_density_m2_reg | 26 | 1.62 |
| raw_acmp | coverage_frac_reg | 26 | 1.90 |
| raw_acmp | local_plane_rms_m | 26 | 1.31 |
| raw_acmp | floater_frac | 26 | 1.33 |
| raw_acmp | label_proxy_frac_all | 26 | 1.30 |

## 주 회귀 계수표

아래 표는 3사양×4결과의 계수다. 모든 predictor는 모델 안에서 표준화했다. 연속 결과는 y도 표준화했다.

| arm | outcome | spec | n | predictor | coef | CI95 |
|---|---|---|---:|---|---:|---|
| raw_dense | assembled | attributes_only | 144 | pt_density_m2_reg | 2.421 | -0.801..5.643 |
| raw_dense | assembled | attributes_only | 144 | coverage_frac_reg | 0.201 | -0.485..0.887 |
| raw_dense | assembled | attributes_only | 144 | local_plane_rms_m | 0.211 | -0.312..0.733 |
| raw_dense | assembled | attributes_only | 144 | floater_frac | -0.142 | -0.563..0.279 |
| raw_dense | assembled | attributes_only | 144 | label_proxy_frac_all | -0.880 | -1.359..-0.401 |
| raw_dense | assembled | observation_only | 199 | median_incidence_deg | -1.050 | -1.532..-0.569 |
| raw_dense | assembled | observation_only | 199 | median_pair_angle_deg | 1.542 | 0.893..2.191 |
| raw_dense | assembled | observation_only | 199 | n_views_nadir | 0.928 | 0.198..1.658 |
| raw_dense | assembled | observation_only | 199 | recon_score_median | -0.219 | -0.953..0.515 |
| raw_dense | assembled | attributes_plus_observation | 144 | pt_density_m2_reg | 1.998 | -1.930..5.926 |
| raw_dense | assembled | attributes_plus_observation | 144 | coverage_frac_reg | -0.116 | -0.963..0.730 |
| raw_dense | assembled | attributes_plus_observation | 144 | local_plane_rms_m | 0.596 | -0.045..1.237 |
| raw_dense | assembled | attributes_plus_observation | 144 | floater_frac | -0.168 | -0.688..0.351 |
| raw_dense | assembled | attributes_plus_observation | 144 | label_proxy_frac_all | -1.014 | -1.581..-0.447 |
| raw_dense | assembled | attributes_plus_observation | 144 | median_incidence_deg | -0.928 | -1.676..-0.180 |
| raw_dense | assembled | attributes_plus_observation | 144 | median_pair_angle_deg | 1.476 | 0.380..2.573 |
| raw_dense | assembled | attributes_plus_observation | 144 | n_views_nadir | -0.283 | -1.455..0.889 |
| raw_dense | assembled | attributes_plus_observation | 144 | recon_score_median | -0.189 | -1.376..0.998 |
| raw_dense | val3dity_valid | attributes_only | 133 | pt_density_m2_reg | 0.202 | -0.553..0.957 |
| raw_dense | val3dity_valid | attributes_only | 133 | coverage_frac_reg | -0.469 | -1.281..0.343 |
| raw_dense | val3dity_valid | attributes_only | 133 | local_plane_rms_m | -0.556 | -1.195..0.084 |
| raw_dense | val3dity_valid | attributes_only | 133 | floater_frac | -0.316 | -0.795..0.163 |
| raw_dense | val3dity_valid | attributes_only | 133 | label_proxy_frac_all | -0.175 | -0.919..0.570 |
| raw_dense | val3dity_valid | observation_only | 179 | median_incidence_deg | 0.075 | -0.559..0.710 |
| raw_dense | val3dity_valid | observation_only | 179 | median_pair_angle_deg | -0.430 | -1.202..0.342 |
| raw_dense | val3dity_valid | observation_only | 179 | n_views_nadir | 0.109 | -0.782..1.001 |
| raw_dense | val3dity_valid | observation_only | 179 | recon_score_median | -0.434 | -1.507..0.640 |
| raw_dense | val3dity_valid | attributes_plus_observation | 133 | pt_density_m2_reg | 0.208 | -0.625..1.041 |
| raw_dense | val3dity_valid | attributes_plus_observation | 133 | coverage_frac_reg | -0.555 | -1.726..0.615 |
| raw_dense | val3dity_valid | attributes_plus_observation | 133 | local_plane_rms_m | -0.631 | -1.310..0.048 |
| raw_dense | val3dity_valid | attributes_plus_observation | 133 | floater_frac | -0.322 | -0.865..0.220 |
| raw_dense | val3dity_valid | attributes_plus_observation | 133 | label_proxy_frac_all | -0.153 | -0.922..0.617 |
| raw_dense | val3dity_valid | attributes_plus_observation | 133 | median_incidence_deg | 0.048 | -0.768..0.865 |
| raw_dense | val3dity_valid | attributes_plus_observation | 133 | median_pair_angle_deg | -0.134 | -0.985..0.717 |
| raw_dense | val3dity_valid | attributes_plus_observation | 133 | n_views_nadir | 0.445 | -0.734..1.625 |
| raw_dense | val3dity_valid | attributes_plus_observation | 133 | recon_score_median | -0.187 | -1.360..0.987 |
| raw_dense | rf_rmse_lod22 | attributes_only | 131 | pt_density_m2_reg | 0.228 | 0.112..0.344 |
| raw_dense | rf_rmse_lod22 | attributes_only | 131 | coverage_frac_reg | -0.059 | -0.166..0.049 |
| raw_dense | rf_rmse_lod22 | attributes_only | 131 | local_plane_rms_m | 0.153 | 0.056..0.251 |
| raw_dense | rf_rmse_lod22 | attributes_only | 131 | floater_frac | -0.005 | -0.100..0.090 |
| raw_dense | rf_rmse_lod22 | attributes_only | 131 | label_proxy_frac_all | -0.039 | -0.139..0.061 |
| raw_dense | rf_rmse_lod22 | observation_only | 131 | median_incidence_deg | -0.003 | -0.106..0.100 |
| raw_dense | rf_rmse_lod22 | observation_only | 131 | median_pair_angle_deg | 0.103 | -0.003..0.209 |
| raw_dense | rf_rmse_lod22 | observation_only | 131 | n_views_nadir | 0.202 | 0.050..0.354 |
| raw_dense | rf_rmse_lod22 | observation_only | 131 | recon_score_median | -0.165 | -0.318..-0.011 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 131 | pt_density_m2_reg | 0.299 | 0.172..0.427 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 131 | coverage_frac_reg | -0.091 | -0.220..0.039 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 131 | local_plane_rms_m | 0.167 | 0.071..0.263 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 131 | floater_frac | 0.011 | -0.087..0.109 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 131 | label_proxy_frac_all | -0.028 | -0.128..0.073 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 131 | median_incidence_deg | 0.118 | 0.012..0.224 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 131 | median_pair_angle_deg | 0.063 | -0.048..0.174 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 131 | n_views_nadir | 0.082 | -0.065..0.228 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 131 | recon_score_median | -0.163 | -0.305..-0.021 |
| raw_dense | rf_roof_planes | attributes_only | 133 | pt_density_m2_reg | -0.032 | -0.124..0.060 |
| raw_dense | rf_roof_planes | attributes_only | 133 | coverage_frac_reg | 0.128 | 0.039..0.218 |
| raw_dense | rf_roof_planes | attributes_only | 133 | local_plane_rms_m | 0.062 | -0.022..0.145 |
| raw_dense | rf_roof_planes | attributes_only | 133 | floater_frac | -0.056 | -0.134..0.022 |
| raw_dense | rf_roof_planes | attributes_only | 133 | label_proxy_frac_all | -0.051 | -0.135..0.032 |
| raw_dense | rf_roof_planes | observation_only | 179 | median_incidence_deg | -0.067 | -0.124..-0.010 |
| raw_dense | rf_roof_planes | observation_only | 179 | median_pair_angle_deg | 0.213 | 0.142..0.284 |
| raw_dense | rf_roof_planes | observation_only | 179 | n_views_nadir | 0.133 | 0.045..0.220 |
| raw_dense | rf_roof_planes | observation_only | 179 | recon_score_median | -0.163 | -0.257..-0.068 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 133 | pt_density_m2_reg | -0.020 | -0.117..0.076 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 133 | coverage_frac_reg | 0.125 | 0.014..0.237 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 133 | local_plane_rms_m | 0.085 | 0.001..0.169 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 133 | floater_frac | -0.030 | -0.110..0.050 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 133 | label_proxy_frac_all | -0.025 | -0.107..0.058 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 133 | median_incidence_deg | -0.019 | -0.109..0.071 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 133 | median_pair_angle_deg | 0.143 | 0.040..0.246 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 133 | n_views_nadir | 0.034 | -0.096..0.164 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 133 | recon_score_median | -0.160 | -0.285..-0.034 |
| raw_lidar | assembled | attributes_only | 198 | pt_density_m2_reg | -0.142 | -0.701..0.417 |
| raw_lidar | assembled | attributes_only | 198 | coverage_frac_reg | 0.317 | -0.041..0.676 |
| raw_lidar | assembled | attributes_only | 198 | local_plane_rms_m | 0.056 | -0.522..0.635 |
| raw_lidar | assembled | attributes_only | 198 | floater_frac | -0.039 | -0.693..0.614 |
| raw_lidar | assembled | attributes_only | 198 | label_proxy_frac_all | 973.279 | -363.410..2309.968 |
| raw_lidar | assembled | observation_only | 199 | median_incidence_deg | -0.534 | -1.087..0.019 |
| raw_lidar | assembled | observation_only | 199 | median_pair_angle_deg | 0.562 | -0.261..1.386 |
| raw_lidar | assembled | observation_only | 199 | n_views_nadir | 0.696 | -0.771..2.163 |
| raw_lidar | assembled | observation_only | 199 | recon_score_median | 0.360 | -0.642..1.362 |
| raw_lidar | assembled | attributes_plus_observation | 198 | pt_density_m2_reg | -0.765 | -1.519..-0.011 |
| raw_lidar | assembled | attributes_plus_observation | 198 | coverage_frac_reg | 0.347 | -0.020..0.713 |
| raw_lidar | assembled | attributes_plus_observation | 198 | local_plane_rms_m | 0.107 | -0.636..0.851 |
| raw_lidar | assembled | attributes_plus_observation | 198 | floater_frac | -0.289 | -1.059..0.482 |
| raw_lidar | assembled | attributes_plus_observation | 198 | label_proxy_frac_all | 549.189 | -787.352..1885.729 |
| raw_lidar | assembled | attributes_plus_observation | 198 | median_incidence_deg | -0.495 | -1.105..0.114 |
| raw_lidar | assembled | attributes_plus_observation | 198 | median_pair_angle_deg | 0.415 | -0.588..1.418 |
| raw_lidar | assembled | attributes_plus_observation | 198 | n_views_nadir | 3.137 | -2.090..8.365 |
| raw_lidar | assembled | attributes_plus_observation | 198 | recon_score_median | 0.711 | -0.547..1.970 |
| raw_lidar | val3dity_valid | attributes_only | 178 | pt_density_m2_reg | -0.368 | -1.015..0.279 |
| raw_lidar | val3dity_valid | attributes_only | 178 | coverage_frac_reg | 0.538 | -0.264..1.340 |
| raw_lidar | val3dity_valid | attributes_only | 178 | local_plane_rms_m | -0.213 | -0.880..0.454 |
| raw_lidar | val3dity_valid | attributes_only | 178 | floater_frac | 0.032 | -0.489..0.552 |
| raw_lidar | val3dity_valid | attributes_only | 178 | label_proxy_frac_all | 0.062 | -0.585..0.710 |
| raw_lidar | val3dity_valid | observation_only | 179 | median_incidence_deg | 0.019 | -0.554..0.591 |
| raw_lidar | val3dity_valid | observation_only | 179 | median_pair_angle_deg | -0.467 | -1.104..0.170 |
| raw_lidar | val3dity_valid | observation_only | 179 | n_views_nadir | -0.089 | -0.982..0.804 |
| raw_lidar | val3dity_valid | observation_only | 179 | recon_score_median | 0.316 | -0.626..1.258 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 178 | pt_density_m2_reg | -0.333 | -1.014..0.347 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 178 | coverage_frac_reg | 0.529 | -0.308..1.367 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 178 | local_plane_rms_m | -0.236 | -0.904..0.431 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 178 | floater_frac | 0.050 | -0.496..0.597 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 178 | label_proxy_frac_all | 0.127 | -0.541..0.796 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 178 | median_incidence_deg | -0.055 | -0.704..0.593 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 178 | median_pair_angle_deg | -0.424 | -1.144..0.296 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 178 | n_views_nadir | -0.096 | -1.079..0.887 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 178 | recon_score_median | 0.277 | -0.756..1.309 |
| raw_lidar | rf_rmse_lod22 | attributes_only | 178 | pt_density_m2_reg | 0.136 | 0.009..0.263 |
| raw_lidar | rf_rmse_lod22 | attributes_only | 178 | coverage_frac_reg | -0.149 | -0.259..-0.039 |
| raw_lidar | rf_rmse_lod22 | attributes_only | 178 | local_plane_rms_m | 0.391 | 0.263..0.519 |
| raw_lidar | rf_rmse_lod22 | attributes_only | 178 | floater_frac | -0.069 | -0.185..0.047 |
| raw_lidar | rf_rmse_lod22 | attributes_only | 178 | label_proxy_frac_all | 0.009 | -0.100..0.118 |
| raw_lidar | rf_rmse_lod22 | observation_only | 178 | median_incidence_deg | -0.105 | -0.224..0.014 |
| raw_lidar | rf_rmse_lod22 | observation_only | 178 | median_pair_angle_deg | 0.139 | 0.000..0.277 |
| raw_lidar | rf_rmse_lod22 | observation_only | 178 | n_views_nadir | 0.361 | 0.180..0.543 |
| raw_lidar | rf_rmse_lod22 | observation_only | 178 | recon_score_median | -0.370 | -0.564..-0.176 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 178 | pt_density_m2_reg | 0.151 | 0.022..0.281 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 178 | coverage_frac_reg | -0.124 | -0.229..-0.018 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 178 | local_plane_rms_m | 0.365 | 0.243..0.488 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 178 | floater_frac | -0.046 | -0.160..0.069 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 178 | label_proxy_frac_all | 0.002 | -0.104..0.109 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 178 | median_incidence_deg | -0.011 | -0.127..0.105 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 178 | median_pair_angle_deg | 0.058 | -0.075..0.190 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 178 | n_views_nadir | 0.338 | 0.170..0.507 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 178 | recon_score_median | -0.342 | -0.524..-0.160 |
| raw_lidar | rf_roof_planes | attributes_only | 178 | pt_density_m2_reg | 0.016 | -0.076..0.108 |
| raw_lidar | rf_roof_planes | attributes_only | 178 | coverage_frac_reg | -0.236 | -0.317..-0.154 |
| raw_lidar | rf_roof_planes | attributes_only | 178 | local_plane_rms_m | 0.101 | 0.009..0.194 |
| raw_lidar | rf_roof_planes | attributes_only | 178 | floater_frac | -0.123 | -0.209..-0.038 |
| raw_lidar | rf_roof_planes | attributes_only | 178 | label_proxy_frac_all | 0.084 | -0.004..0.172 |
| raw_lidar | rf_roof_planes | observation_only | 178 | median_incidence_deg | -0.170 | -0.253..-0.088 |
| raw_lidar | rf_roof_planes | observation_only | 178 | median_pair_angle_deg | 0.182 | 0.084..0.281 |
| raw_lidar | rf_roof_planes | observation_only | 178 | n_views_nadir | 0.096 | -0.027..0.220 |
| raw_lidar | rf_roof_planes | observation_only | 178 | recon_score_median | -0.261 | -0.395..-0.127 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 178 | pt_density_m2_reg | -0.010 | -0.104..0.084 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 178 | coverage_frac_reg | -0.225 | -0.303..-0.147 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 178 | local_plane_rms_m | 0.080 | -0.008..0.169 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 178 | floater_frac | -0.084 | -0.169..-0.000 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 178 | label_proxy_frac_all | 0.088 | 0.003..0.173 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 178 | median_incidence_deg | -0.160 | -0.248..-0.071 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 178 | median_pair_angle_deg | 0.165 | 0.062..0.268 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 178 | n_views_nadir | 0.080 | -0.047..0.206 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 178 | recon_score_median | -0.236 | -0.374..-0.097 |
| raw_acmp | assembled | attributes_only | 26 | pt_density_m2_reg | -1.285 | -3.545..0.976 |
| raw_acmp | assembled | attributes_only | 26 | coverage_frac_reg | -0.731 | -2.155..0.692 |
| raw_acmp | assembled | attributes_only | 26 | local_plane_rms_m | -0.188 | -1.388..1.012 |
| raw_acmp | assembled | attributes_only | 26 | floater_frac | 10.229 | -2.668..23.127 |
| raw_acmp | assembled | attributes_only | 26 | label_proxy_frac_all | -0.609 | -1.704..0.487 |
| raw_acmp | assembled | observation_only | 64 | median_incidence_deg | 0.207 | -0.473..0.887 |
| raw_acmp | assembled | observation_only | 64 | median_pair_angle_deg | 0.640 | -0.314..1.593 |
| raw_acmp | assembled | observation_only | 64 | n_views_nadir | 0.382 | -0.337..1.101 |
| raw_acmp | assembled | observation_only | 64 | recon_score_median | -0.444 | -1.524..0.636 |
| raw_acmp | assembled | attributes_plus_observation | 26 | pt_density_m2_reg | 0.449 | -4.573..5.470 |
| raw_acmp | assembled | attributes_plus_observation | 26 | coverage_frac_reg | -0.619 | -2.873..1.634 |
| raw_acmp | assembled | attributes_plus_observation | 26 | local_plane_rms_m | 1.619 | -0.772..4.010 |
| raw_acmp | assembled | attributes_plus_observation | 26 | floater_frac | 3.251 | -9.550..16.053 |
| raw_acmp | assembled | attributes_plus_observation | 26 | label_proxy_frac_all | 0.159 | -1.148..1.466 |
| raw_acmp | assembled | attributes_plus_observation | 26 | median_incidence_deg | 1.583 | -1.293..4.458 |
| raw_acmp | assembled | attributes_plus_observation | 26 | median_pair_angle_deg | 2.357 | -2.359..7.074 |
| raw_acmp | assembled | attributes_plus_observation | 26 | n_views_nadir | 0.630 | -2.953..4.212 |
| raw_acmp | assembled | attributes_plus_observation | 26 | recon_score_median | -2.033 | -8.578..4.512 |
| raw_acmp | val3dity_valid | attributes_only | 26 | pt_density_m2_reg | -0.974 | -3.123..1.176 |
| raw_acmp | val3dity_valid | attributes_only | 26 | coverage_frac_reg | -0.509 | -1.956..0.937 |
| raw_acmp | val3dity_valid | attributes_only | 26 | local_plane_rms_m | 0.400 | -1.108..1.908 |
| raw_acmp | val3dity_valid | attributes_only | 26 | floater_frac | 6.144 | -5.263..17.551 |
| raw_acmp | val3dity_valid | attributes_only | 26 | label_proxy_frac_all | -3.619 | -10.639..3.400 |
| raw_acmp | val3dity_valid | observation_only | 64 | median_incidence_deg | 0.251 | -0.475..0.977 |
| raw_acmp | val3dity_valid | observation_only | 64 | median_pair_angle_deg | 0.735 | -0.252..1.722 |
| raw_acmp | val3dity_valid | observation_only | 64 | n_views_nadir | 0.402 | -0.330..1.133 |
| raw_acmp | val3dity_valid | observation_only | 64 | recon_score_median | -0.418 | -1.531..0.695 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 26 | pt_density_m2_reg | -8.921 | -20.516..2.674 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 26 | coverage_frac_reg | 6.329 | -1.685..14.344 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 26 | local_plane_rms_m | 2.085 | -1.801..5.971 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 26 | floater_frac | 4.255 | -5.487..13.998 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 26 | label_proxy_frac_all | -6.558 | -13.854..0.738 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 26 | median_incidence_deg | 1.767 | -3.310..6.844 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 26 | median_pair_angle_deg | 10.905 | -1.952..23.762 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 26 | n_views_nadir | 14.783 | -2.100..31.665 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 26 | recon_score_median | -13.856 | -30.941..3.229 |
| raw_acmp | rf_rmse_lod22 | attributes_only | 23 | pt_density_m2_reg | 0.227 | -0.015..0.469 |
| raw_acmp | rf_rmse_lod22 | attributes_only | 23 | coverage_frac_reg | -0.164 | -0.445..0.117 |
| raw_acmp | rf_rmse_lod22 | attributes_only | 23 | local_plane_rms_m | 0.003 | -0.193..0.199 |
| raw_acmp | rf_rmse_lod22 | attributes_only | 23 | floater_frac | 0.265 | 0.071..0.459 |
| raw_acmp | rf_rmse_lod22 | attributes_only | 23 | label_proxy_frac_all | 0.039 | -0.208..0.286 |
| raw_acmp | rf_rmse_lod22 | observation_only | 37 | median_incidence_deg | 0.347 | 0.086..0.608 |
| raw_acmp | rf_rmse_lod22 | observation_only | 37 | median_pair_angle_deg | 0.045 | -0.417..0.507 |
| raw_acmp | rf_rmse_lod22 | observation_only | 37 | n_views_nadir | 0.071 | -0.207..0.349 |
| raw_acmp | rf_rmse_lod22 | observation_only | 37 | recon_score_median | -0.216 | -0.732..0.301 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | pt_density_m2_reg | 0.607 | 0.249..0.965 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | coverage_frac_reg | -0.210 | -0.425..0.006 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | local_plane_rms_m | 0.075 | -0.103..0.253 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | floater_frac | 0.166 | -0.022..0.353 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | label_proxy_frac_all | 0.124 | -0.093..0.340 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | median_incidence_deg | 0.260 | 0.071..0.448 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | median_pair_angle_deg | 0.351 | 0.021..0.681 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | n_views_nadir | -0.102 | -0.344..0.140 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | recon_score_median | -0.586 | -1.007..-0.166 |
| raw_acmp | rf_roof_planes | attributes_only | 26 | pt_density_m2_reg | -0.193 | -0.550..0.164 |
| raw_acmp | rf_roof_planes | attributes_only | 26 | coverage_frac_reg | 0.069 | -0.318..0.457 |
| raw_acmp | rf_roof_planes | attributes_only | 26 | local_plane_rms_m | 0.490 | 0.156..0.824 |
| raw_acmp | rf_roof_planes | attributes_only | 26 | floater_frac | -0.135 | -0.466..0.196 |
| raw_acmp | rf_roof_planes | attributes_only | 26 | label_proxy_frac_all | 0.018 | -0.301..0.337 |
| raw_acmp | rf_roof_planes | observation_only | 64 | median_incidence_deg | -0.459 | -0.670..-0.248 |
| raw_acmp | rf_roof_planes | observation_only | 64 | median_pair_angle_deg | 0.262 | -0.037..0.561 |
| raw_acmp | rf_roof_planes | observation_only | 64 | n_views_nadir | 0.001 | -0.245..0.247 |
| raw_acmp | rf_roof_planes | observation_only | 64 | recon_score_median | -0.187 | -0.521..0.148 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 26 | pt_density_m2_reg | -0.359 | -1.340..0.623 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 26 | coverage_frac_reg | 0.106 | -0.385..0.597 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 26 | local_plane_rms_m | 0.463 | -0.047..0.973 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 26 | floater_frac | -0.176 | -0.660..0.307 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 26 | label_proxy_frac_all | 0.003 | -0.393..0.398 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 26 | median_incidence_deg | -0.312 | -0.802..0.178 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 26 | median_pair_angle_deg | 0.483 | -0.427..1.393 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 26 | n_views_nadir | 0.226 | -0.594..1.046 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 26 | recon_score_median | -0.250 | -1.428..0.928 |

## 연속 결과 Spearman

| arm | outcome | axis | n | Spearman rho |
|---|---|---|---:|---:|
| raw_dense | rf_rmse_lod22 | pt_density_m2_reg | 131 | 0.339 |
| raw_dense | rf_rmse_lod22 | coverage_frac_reg | 131 | 0.262 |
| raw_dense | rf_rmse_lod22 | local_plane_rms_m | 131 | 0.429 |
| raw_dense | rf_rmse_lod22 | floater_frac | 131 | 0.263 |
| raw_dense | rf_rmse_lod22 | label_proxy_frac_all | 131 | -0.188 |
| raw_dense | rf_rmse_lod22 | m3c2_rms_m | 130 | 0.120 |
| raw_dense | rf_roof_planes | pt_density_m2_reg | 179 | 0.772 |
| raw_dense | rf_roof_planes | coverage_frac_reg | 179 | 0.745 |
| raw_dense | rf_roof_planes | local_plane_rms_m | 133 | 0.343 |
| raw_dense | rf_roof_planes | floater_frac | 140 | 0.198 |
| raw_dense | rf_roof_planes | label_proxy_frac_all | 140 | -0.396 |
| raw_dense | rf_roof_planes | m3c2_rms_m | 132 | 0.199 |
| raw_lidar | rf_rmse_lod22 | pt_density_m2_reg | 178 | 0.314 |
| raw_lidar | rf_rmse_lod22 | coverage_frac_reg | 178 | -0.084 |
| raw_lidar | rf_rmse_lod22 | local_plane_rms_m | 178 | 0.492 |
| raw_lidar | rf_rmse_lod22 | floater_frac | 178 | 0.083 |
| raw_lidar | rf_rmse_lod22 | label_proxy_frac_all | 178 | -0.034 |
| raw_lidar | rf_rmse_lod22 | m3c2_rms_m | 0 | none |
| raw_lidar | rf_roof_planes | pt_density_m2_reg | 178 | 0.103 |
| raw_lidar | rf_roof_planes | coverage_frac_reg | 178 | -0.189 |
| raw_lidar | rf_roof_planes | local_plane_rms_m | 178 | 0.187 |
| raw_lidar | rf_roof_planes | floater_frac | 178 | 0.146 |
| raw_lidar | rf_roof_planes | label_proxy_frac_all | 178 | 0.136 |
| raw_lidar | rf_roof_planes | m3c2_rms_m | 0 | none |
| raw_acmp | rf_rmse_lod22 | pt_density_m2_reg | 37 | -0.415 |
| raw_acmp | rf_rmse_lod22 | coverage_frac_reg | 37 | -0.524 |
| raw_acmp | rf_rmse_lod22 | local_plane_rms_m | 23 | 0.094 |
| raw_acmp | rf_rmse_lod22 | floater_frac | 37 | 0.581 |
| raw_acmp | rf_rmse_lod22 | label_proxy_frac_all | 37 | -0.016 |
| raw_acmp | rf_rmse_lod22 | m3c2_rms_m | 27 | 0.420 |
| raw_acmp | rf_roof_planes | pt_density_m2_reg | 64 | 0.519 |
| raw_acmp | rf_roof_planes | coverage_frac_reg | 64 | 0.513 |
| raw_acmp | rf_roof_planes | local_plane_rms_m | 26 | 0.534 |
| raw_acmp | rf_roof_planes | floater_frac | 63 | -0.397 |
| raw_acmp | rf_roof_planes | label_proxy_frac_all | 63 | -0.211 |
| raw_acmp | rf_roof_planes | m3c2_rms_m | 31 | 0.002 |

## 로버스트·감도

로버스트 제외 재추정(속성+관측기하 사양):

| arm | outcome | spec | n | predictor | coef | CI95 |
|---|---|---|---:|---|---:|---|
| raw_dense | assembled | attributes_plus_observation | 141 | pt_density_m2_reg | 9.088 | -3.006..21.182 |
| raw_dense | assembled | attributes_plus_observation | 141 | coverage_frac_reg | -0.834 | -2.143..0.476 |
| raw_dense | assembled | attributes_plus_observation | 141 | local_plane_rms_m | 0.541 | -0.145..1.227 |
| raw_dense | assembled | attributes_plus_observation | 141 | floater_frac | -0.079 | -0.609..0.452 |
| raw_dense | assembled | attributes_plus_observation | 141 | label_proxy_frac_all | -0.949 | -1.542..-0.356 |
| raw_dense | assembled | attributes_plus_observation | 141 | median_incidence_deg | -1.051 | -1.864..-0.238 |
| raw_dense | assembled | attributes_plus_observation | 141 | median_pair_angle_deg | 1.472 | 0.181..2.763 |
| raw_dense | assembled | attributes_plus_observation | 141 | n_views_nadir | -0.133 | -1.528..1.261 |
| raw_dense | assembled | attributes_plus_observation | 141 | recon_score_median | -0.208 | -1.515..1.098 |
| raw_dense | val3dity_valid | attributes_plus_observation | 130 | pt_density_m2_reg | 0.001 | -0.854..0.856 |
| raw_dense | val3dity_valid | attributes_plus_observation | 130 | coverage_frac_reg | -0.523 | -1.718..0.671 |
| raw_dense | val3dity_valid | attributes_plus_observation | 130 | local_plane_rms_m | -0.654 | -1.347..0.038 |
| raw_dense | val3dity_valid | attributes_plus_observation | 130 | floater_frac | -0.322 | -0.867..0.224 |
| raw_dense | val3dity_valid | attributes_plus_observation | 130 | label_proxy_frac_all | -0.183 | -0.972..0.606 |
| raw_dense | val3dity_valid | attributes_plus_observation | 130 | median_incidence_deg | 0.002 | -0.853..0.858 |
| raw_dense | val3dity_valid | attributes_plus_observation | 130 | median_pair_angle_deg | -0.103 | -0.976..0.769 |
| raw_dense | val3dity_valid | attributes_plus_observation | 130 | n_views_nadir | 0.447 | -0.731..1.626 |
| raw_dense | val3dity_valid | attributes_plus_observation | 130 | recon_score_median | -0.182 | -1.342..0.977 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 128 | pt_density_m2_reg | 0.209 | 0.084..0.333 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 128 | coverage_frac_reg | -0.089 | -0.226..0.047 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 128 | local_plane_rms_m | 0.180 | 0.079..0.281 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 128 | floater_frac | 0.015 | -0.088..0.118 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 128 | label_proxy_frac_all | -0.031 | -0.136..0.074 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 128 | median_incidence_deg | 0.094 | -0.019..0.207 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 128 | median_pair_angle_deg | 0.083 | -0.033..0.200 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 128 | n_views_nadir | 0.123 | -0.032..0.278 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | 128 | recon_score_median | -0.180 | -0.327..-0.033 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 130 | pt_density_m2_reg | 0.061 | -0.048..0.171 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 130 | coverage_frac_reg | 0.106 | -0.003..0.214 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 130 | local_plane_rms_m | 0.094 | 0.011..0.176 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 130 | floater_frac | -0.027 | -0.105..0.051 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 130 | label_proxy_frac_all | -0.014 | -0.095..0.066 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 130 | median_incidence_deg | 0.002 | -0.090..0.094 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 130 | median_pair_angle_deg | 0.132 | 0.031..0.233 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 130 | n_views_nadir | 0.010 | -0.118..0.139 |
| raw_dense | rf_roof_planes | attributes_plus_observation | 130 | recon_score_median | -0.152 | -0.271..-0.033 |
| raw_lidar | assembled | attributes_plus_observation | 195 | pt_density_m2_reg | -0.736 | -1.462..-0.011 |
| raw_lidar | assembled | attributes_plus_observation | 195 | coverage_frac_reg | 0.349 | -0.020..0.719 |
| raw_lidar | assembled | attributes_plus_observation | 195 | local_plane_rms_m | 0.103 | -0.616..0.822 |
| raw_lidar | assembled | attributes_plus_observation | 195 | floater_frac | -0.288 | -1.057..0.481 |
| raw_lidar | assembled | attributes_plus_observation | 195 | label_proxy_frac_all | 553.900 | -792.152..1899.952 |
| raw_lidar | assembled | attributes_plus_observation | 195 | median_incidence_deg | -0.496 | -1.107..0.114 |
| raw_lidar | assembled | attributes_plus_observation | 195 | median_pair_angle_deg | 0.419 | -0.589..1.426 |
| raw_lidar | assembled | attributes_plus_observation | 195 | n_views_nadir | 3.007 | -2.095..8.110 |
| raw_lidar | assembled | attributes_plus_observation | 195 | recon_score_median | 0.702 | -0.542..1.947 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 175 | pt_density_m2_reg | -0.390 | -1.087..0.306 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 175 | coverage_frac_reg | 0.537 | -0.309..1.382 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 175 | local_plane_rms_m | -0.326 | -1.020..0.368 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 175 | floater_frac | 0.072 | -0.469..0.614 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 175 | label_proxy_frac_all | 0.133 | -0.539..0.805 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 175 | median_incidence_deg | -0.056 | -0.700..0.589 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 175 | median_pair_angle_deg | -0.423 | -1.148..0.302 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 175 | n_views_nadir | -0.119 | -1.074..0.837 |
| raw_lidar | val3dity_valid | attributes_plus_observation | 175 | recon_score_median | 0.274 | -0.742..1.289 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 175 | pt_density_m2_reg | 0.160 | 0.025..0.295 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 175 | coverage_frac_reg | -0.146 | -0.259..-0.032 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 175 | local_plane_rms_m | 0.355 | 0.227..0.482 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 175 | floater_frac | -0.051 | -0.173..0.071 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 175 | label_proxy_frac_all | 0.014 | -0.101..0.129 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 175 | median_incidence_deg | -0.014 | -0.138..0.110 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 175 | median_pair_angle_deg | 0.080 | -0.062..0.222 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 175 | n_views_nadir | 0.334 | 0.157..0.510 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | 175 | recon_score_median | -0.394 | -0.587..-0.201 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 175 | pt_density_m2_reg | -0.009 | -0.103..0.084 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 175 | coverage_frac_reg | -0.224 | -0.303..-0.144 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 175 | local_plane_rms_m | 0.091 | 0.003..0.179 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 175 | floater_frac | -0.085 | -0.170..0.001 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 175 | label_proxy_frac_all | 0.085 | -0.002..0.171 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 175 | median_incidence_deg | -0.160 | -0.250..-0.071 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 175 | median_pair_angle_deg | 0.163 | 0.059..0.267 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 175 | n_views_nadir | 0.083 | -0.042..0.209 |
| raw_lidar | rf_roof_planes | attributes_plus_observation | 175 | recon_score_median | -0.228 | -0.366..-0.091 |
| raw_acmp | assembled | attributes_plus_observation | 25 | pt_density_m2_reg | 204.224 | -5382.688..5791.136 |
| raw_acmp | assembled | attributes_plus_observation | 25 | coverage_frac_reg | -74.616 | -3964.264..3815.031 |
| raw_acmp | assembled | attributes_plus_observation | 25 | local_plane_rms_m | 28.398 | -3993.046..4049.842 |
| raw_acmp | assembled | attributes_plus_observation | 25 | floater_frac | 283.783 | -4608.053..5175.620 |
| raw_acmp | assembled | attributes_plus_observation | 25 | label_proxy_frac_all | 5.910 | -2942.423..2954.243 |
| raw_acmp | assembled | attributes_plus_observation | 25 | median_incidence_deg | 58.078 | -3252.495..3368.650 |
| raw_acmp | assembled | attributes_plus_observation | 25 | median_pair_angle_deg | 70.707 | -6622.520..6763.933 |
| raw_acmp | assembled | attributes_plus_observation | 25 | n_views_nadir | 129.064 | -4369.909..4628.037 |
| raw_acmp | assembled | attributes_plus_observation | 25 | recon_score_median | -181.190 | -8335.363..7972.984 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 25 | pt_density_m2_reg | 25478736.885 | 25468287.880..25489185.891 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 25 | coverage_frac_reg | 6951247.575 | 6944317.346..6958177.803 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 25 | local_plane_rms_m | 12597992.581 | 12591711.498..12604273.664 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 25 | floater_frac | 16640387.767 | 16634313.241..16646462.294 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 25 | label_proxy_frac_all | -15770292.138 | -15775172.181..-15765412.094 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 25 | median_incidence_deg | 13587931.306 | 13582024.986..13593837.625 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 25 | median_pair_angle_deg | 54158632.237 | 54147427.929..54169836.545 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 25 | n_views_nadir | 61570121.085 | 61563309.033..61576933.138 |
| raw_acmp | val3dity_valid | attributes_plus_observation | 25 | recon_score_median | -64023384.595 | -64036812.874..-64009956.316 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | pt_density_m2_reg | 0.607 | 0.249..0.965 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | coverage_frac_reg | -0.210 | -0.425..0.006 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | local_plane_rms_m | 0.075 | -0.103..0.253 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | floater_frac | 0.166 | -0.022..0.353 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | label_proxy_frac_all | 0.124 | -0.093..0.340 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | median_incidence_deg | 0.260 | 0.071..0.448 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | median_pair_angle_deg | 0.351 | 0.021..0.681 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | n_views_nadir | -0.102 | -0.344..0.140 |
| raw_acmp | rf_rmse_lod22 | attributes_plus_observation | 23 | recon_score_median | -0.586 | -1.007..-0.166 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 25 | pt_density_m2_reg | 0.218 | -0.651..1.086 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 25 | coverage_frac_reg | -0.093 | -0.673..0.486 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 25 | local_plane_rms_m | 0.338 | -0.193..0.870 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 25 | floater_frac | -0.053 | -0.565..0.459 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 25 | label_proxy_frac_all | 0.006 | -0.397..0.409 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 25 | median_incidence_deg | -0.425 | -0.914..0.064 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 25 | median_pair_angle_deg | 0.517 | -0.414..1.447 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 25 | n_views_nadir | 0.119 | -0.442..0.681 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | 25 | recon_score_median | -0.445 | -1.559..0.669 |

run_2 결과 변수 교체 감도(겹치는 93동, 속성+관측기하 사양의 속성 계수만 비교):

| arm | outcome | common_attr_coef | sign_matches | median_abs_coef_ratio | IQR |
|---|---|---:|---:|---:|---|
| raw_dense | assembled | 5 | 5 | 1.315 | 1.12-1.43 |
| raw_dense | val3dity_valid | 5 | 4 | 2.003 | 0.616-2.67 |
| raw_dense | rf_rmse_lod22 | 5 | 5 | 1.558 | 0.862-2.06 |
| raw_dense | rf_roof_planes | 5 | 5 | 1.115 | 1.1-1.28 |
| raw_lidar | assembled | 0 | 0 | none | None |
| raw_lidar | val3dity_valid | 5 | 4 | 1.511 | 0.274-2.39 |
| raw_lidar | rf_rmse_lod22 | 5 | 5 | 0.991 | 0.989-1 |
| raw_lidar | rf_roof_planes | 5 | 5 | 1.108 | 1.01-1.12 |

- run_2 감도 전체: 속성 계수 부호 일치 33/35, |계수| 비율 중앙값 1.315.

label_proxy_frac_ground 교체 감도(속성+관측기하 사양):

| arm | outcome | common_attr_coef | sign_matches | median_abs_coef_ratio | IQR |
|---|---|---:|---:|---:|---|
| raw_dense | assembled | 5 | 4 | 0.871 | 0.743-1.8 |
| raw_dense | val3dity_valid | 5 | 5 | 1.573 | 1.14-2.46 |
| raw_dense | rf_rmse_lod22 | 5 | 4 | 0.967 | 0.941-1.13 |
| raw_dense | rf_roof_planes | 5 | 4 | 1.066 | 0.971-1.33 |
| raw_lidar | assembled | 5 | 3 | 3.366 | 1.67-4.4 |
| raw_lidar | val3dity_valid | 5 | 4 | 1.260 | 0.993-1.34 |
| raw_lidar | rf_rmse_lod22 | 5 | 4 | 1.072 | 0.833-1.13 |
| raw_lidar | rf_roof_planes | 5 | 5 | 1.510 | 1.29-1.76 |
| raw_acmp | assembled | 5 | 4 | 55.486 | 34.6-444 |
| raw_acmp | val3dity_valid | 5 | 3 | 23.122 | 10.4-29.5 |
| raw_acmp | rf_rmse_lod22 | 5 | 4 | 1.206 | 1.03-1.35 |
| raw_acmp | rf_roof_planes | 5 | 2 | 1.950 | 1.49-2.11 |

fallback clip_source 더미 추가 감도(속성+관측기하 사양):

| arm | outcome | common_attr_coef | sign_matches | median_abs_coef_ratio | IQR |
|---|---|---:|---:|---:|---|
| raw_dense | assembled | 5 | 4 | 2.033 | 1.98-5.01 |
| raw_dense | val3dity_valid | 5 | 5 | 1.025 | 0.961-1.1 |
| raw_dense | rf_rmse_lod22 | 5 | 4 | 1.326 | 1.06-3.16 |
| raw_dense | rf_roof_planes | 5 | 4 | 0.811 | 0.61-0.95 |
| raw_lidar | assembled | 5 | 4 | 0.763 | 0.588-2.35 |
| raw_lidar | val3dity_valid | 5 | 2 | 0.965 | 0.691-1.06 |
| raw_lidar | rf_rmse_lod22 | 5 | 5 | 0.927 | 0.891-1.02 |
| raw_lidar | rf_roof_planes | 5 | 4 | 0.810 | 0.535-0.946 |
| raw_acmp | assembled | 5 | 5 | 1.000 | 1-1 |
| raw_acmp | val3dity_valid | 5 | 5 | 1.000 | 1-1 |
| raw_acmp | rf_rmse_lod22 | 5 | 5 | 1.000 | 1-1 |
| raw_acmp | rf_roof_planes | 5 | 5 | 1.000 | 1-1 |

감도 계수 전수는 `docs/attr_outcome_regression_sensitivity_v1.csv`에 기록했다.

일반 추정(OLS)과 로버스트 추정(Huber) 부호 불일치:

| arm | outcome | spec | predictor | robust | ordinary | note |
|---|---|---|---|---:|---:|---|
| raw_dense | rf_rmse_lod22 | attributes_only | label_proxy_frac_all | -0.039 | 0.235 | 소수 사례 의존 기록 |
| raw_dense | rf_rmse_lod22 | observation_only | median_incidence_deg | -0.003 | 0.105 | 소수 사례 의존 기록 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | floater_frac | 0.011 | -0.031 | 소수 사례 의존 기록 |
| raw_dense | rf_rmse_lod22 | attributes_plus_observation | label_proxy_frac_all | -0.028 | 0.237 | 소수 사례 의존 기록 |
| raw_dense | rf_roof_planes | attributes_only | label_proxy_frac_all | -0.051 | 0.014 | 소수 사례 의존 기록 |
| raw_dense | rf_roof_planes | attributes_plus_observation | pt_density_m2_reg | -0.020 | 0.005 | 소수 사례 의존 기록 |
| raw_dense | rf_roof_planes | attributes_plus_observation | label_proxy_frac_all | -0.025 | 0.049 | 소수 사례 의존 기록 |
| raw_dense | rf_roof_planes | attributes_plus_observation | median_incidence_deg | -0.019 | 0.057 | 소수 사례 의존 기록 |
| raw_lidar | rf_rmse_lod22 | attributes_only | label_proxy_frac_all | 0.009 | -0.001 | 소수 사례 의존 기록 |
| raw_lidar | rf_rmse_lod22 | attributes_plus_observation | label_proxy_frac_all | 0.002 | -0.015 | 소수 사례 의존 기록 |
| raw_acmp | rf_rmse_lod22 | attributes_only | local_plane_rms_m | 0.003 | -0.057 | 소수 사례 의존 기록 |
| raw_acmp | rf_rmse_lod22 | observation_only | median_pair_angle_deg | 0.045 | -0.134 | 소수 사례 의존 기록 |
| raw_acmp | rf_rmse_lod22 | observation_only | n_views_nadir | 0.071 | -0.011 | 소수 사례 의존 기록 |
| raw_acmp | rf_roof_planes | attributes_only | label_proxy_frac_all | 0.018 | -0.002 | 소수 사례 의존 기록 |
| raw_acmp | rf_roof_planes | attributes_plus_observation | label_proxy_frac_all | 0.003 | -0.023 | 소수 사례 의존 기록 |

## 영향점 진단

Cook's distance > 4/n 목록(속성+관측기하 사양):

| arm | outcome | n | threshold | n_ids | IDs |
|---|---|---:|---:|---:|---|
| raw_dense | assembled | 144 | 0.0278 | 13 | DEBY_LOD2_104586480;DEBY_LOD2_4907017;DEBY_LOD2_4907165;DEBY_LOD2_4907169;DEBY_LOD2_4907176;DEBY_LOD2_4907182;DEBY_LOD2_4907508;DEBY_LOD2_4907510;DEBY_LOD2_4908163;DEBY_LOD2_4908165;DEBY_LOD2_4908178;DEBY_LOD2_4959465;DEBY_LOD2_4959758 |
| raw_dense | val3dity_valid | 133 | 0.0301 | 9 | DEBY_LOD2_4906975;DEBY_LOD2_4906985;DEBY_LOD2_4907017;DEBY_LOD2_4907025;DEBY_LOD2_4907519;DEBY_LOD2_4907520;DEBY_LOD2_4908163;DEBY_LOD2_4959326;DEBY_LOD2_60042 |
| raw_dense | rf_rmse_lod22 | 131 | 0.0305 | 10 | DEBY_LOD2_108250120;DEBY_LOD2_42364663;DEBY_LOD2_4906984;DEBY_LOD2_4907017;DEBY_LOD2_4907168;DEBY_LOD2_4907176;DEBY_LOD2_4907198;DEBY_LOD2_4908163;DEBY_LOD2_4959320;DEBY_LOD2_4959460 |
| raw_dense | rf_roof_planes | 133 | 0.0301 | 8 | DEBY_LOD2_108580336;DEBY_LOD2_42364663;DEBY_LOD2_4906965;DEBY_LOD2_4906968;DEBY_LOD2_4906975;DEBY_LOD2_4907017;DEBY_LOD2_4959326;DEBY_LOD2_60042 |
| raw_lidar | assembled | 198 | 0.0202 | 17 | DEBY_LOD2_108247349;DEBY_LOD2_42364661;DEBY_LOD2_4907000;DEBY_LOD2_4907035;DEBY_LOD2_4907156;DEBY_LOD2_4907164;DEBY_LOD2_4907166;DEBY_LOD2_4908059;DEBY_LOD2_4908165;DEBY_LOD2_4908172;DEBY_LOD2_4908179;DEBY_LOD2_4959320;DEBY_LOD2_4959465;DEBY_LOD2_4959759;DEBY_LOD2_60109;DEBY_LOD2_8573617;DEBY_LOD2_8573847 |
| raw_lidar | val3dity_valid | 178 | 0.0225 | 15 | DEBY_LOD2_108250120;DEBY_LOD2_108580336;DEBY_LOD2_42364607;DEBY_LOD2_4906965;DEBY_LOD2_4906967;DEBY_LOD2_4906980;DEBY_LOD2_4906998;DEBY_LOD2_4907176;DEBY_LOD2_4907178;DEBY_LOD2_4907184;DEBY_LOD2_4907506;DEBY_LOD2_4907514;DEBY_LOD2_4908159;DEBY_LOD2_4959753;DEBY_LOD2_8573848 |
| raw_lidar | rf_rmse_lod22 | 178 | 0.0225 | 10 | DEBY_LOD2_104586480;DEBY_LOD2_42364663;DEBY_LOD2_42364665;DEBY_LOD2_42364667;DEBY_LOD2_4906970;DEBY_LOD2_4906982;DEBY_LOD2_4908165;DEBY_LOD2_4908354;DEBY_LOD2_4959320;DEBY_LOD2_4959753 |
| raw_lidar | rf_roof_planes | 178 | 0.0225 | 12 | DEBY_LOD2_108580336;DEBY_LOD2_42364659;DEBY_LOD2_4906965;DEBY_LOD2_4906967;DEBY_LOD2_4906977;DEBY_LOD2_4906980;DEBY_LOD2_4906984;DEBY_LOD2_4907519;DEBY_LOD2_4959320;DEBY_LOD2_4959326;DEBY_LOD2_4959460;DEBY_LOD2_60042 |
| raw_acmp | assembled | 26 | 0.1538 | 8 | DEBY_LOD2_104586480;DEBY_LOD2_4907169;DEBY_LOD2_4907175;DEBY_LOD2_4907181;DEBY_LOD2_4908046;DEBY_LOD2_4908169;DEBY_LOD2_4908176;DEBY_LOD2_8568392 |
| raw_acmp | val3dity_valid | 26 | 0.1538 | 7 | DEBY_LOD2_104586480;DEBY_LOD2_4907033;DEBY_LOD2_4907169;DEBY_LOD2_4907181;DEBY_LOD2_4908046;DEBY_LOD2_4908169;DEBY_LOD2_8568392 |
| raw_acmp | rf_rmse_lod22 | 23 | 0.1739 | 6 | DEBY_LOD2_108247350;DEBY_LOD2_4907016;DEBY_LOD2_4907175;DEBY_LOD2_4908169;DEBY_LOD2_4959758;DEBY_LOD2_8568392 |
| raw_acmp | rf_roof_planes | 26 | 0.1538 | 2 | DEBY_LOD2_104586480;DEBY_LOD2_4907175 |

영향점 제외 재추정 계수는 `docs/attr_outcome_regression_coefficients_v1.csv`의 `*_cook_excluded` variant에 기록했다. 영향점 목록 전수는 `docs/attr_outcome_regression_diagnostics_v1.csv`에 기록했다.

## 층화 병기

| arm | lens | stratum | n | assembled_rate | valid_rate | rmse_median | density_median | coverage_median |
|---|---|---|---:|---:|---:|---:|---:|---:|
| raw_dense | complexity | high | 54 | 0.815 | 0.843 | 1.656 | 169.670 | 0.995 |
| raw_dense | complexity | low | 123 | 0.455 | 0.972 | 0.730 | 7.702 | 0.377 |
| raw_dense | complexity | mid | 22 | 0.682 | 0.905 | 1.910 | 140.272 | 0.921 |
| raw_dense | size | high | 66 | 0.773 | 0.845 | 1.775 | 177.939 | 0.981 |
| raw_dense | size | low | 66 | 0.424 | 0.967 | 0.525 | 10.618 | 0.372 |
| raw_dense | size | mid | 67 | 0.537 | 0.967 | 1.046 | 6.908 | 0.395 |
| raw_dense | observation | high | 66 | 0.848 | 0.894 | 1.324 | 303.857 | 1.000 |
| raw_dense | observation | low | 66 | 0.348 | 0.981 | 1.178 | 0.164 | 0.022 |
| raw_dense | observation | mid | 67 | 0.537 | 0.917 | 1.179 | 17.094 | 0.500 |
| raw_dense | manual_failure_label | 가림 | 11 | 0.000 | 1.000 | none | 0.000 | 0.000 |
| raw_dense | manual_failure_label | 관측각·커버리지 | 17 | 0.000 | 1.000 | none | 0.000 | 0.000 |
| raw_dense | manual_failure_label | 무텍스처 | 4 | 0.000 | 1.000 | none | 0.416 | 0.033 |
| raw_dense | manual_failure_label | 복합(세장+관측각) | 1 | 0.000 | 1.000 | none | 0.000 | 0.000 |
| raw_dense | manual_failure_label | 복합(소형+가림) | 4 | 0.000 | 1.000 | none | 0.536 | 0.062 |
| raw_dense | manual_failure_label | 복합(소형+재질) | 4 | 0.000 | 1.000 | none | 0.000 | 0.000 |
| raw_dense | manual_failure_label | 복합(스침각+가림) | 1 | 0.000 | 1.000 | none | 0.000 | 0.000 |
| raw_dense | manual_failure_label | 복합(재질+가림) | 1 | 0.000 | 1.000 | none | 0.000 | 0.000 |
| raw_dense | manual_failure_label | 복합(저조도+가림) | 1 | 0.000 | 1.000 | none | 0.169 | 0.031 |
| raw_lidar | complexity | high | 54 | 0.944 | 0.804 | 1.742 | 18.714 | 0.997 |
| raw_lidar | complexity | low | 123 | 0.862 | 0.953 | 1.156 | 18.518 | 0.999 |
| raw_lidar | complexity | mid | 22 | 0.955 | 1.000 | 2.063 | 18.920 | 0.997 |
| raw_lidar | size | high | 66 | 0.879 | 0.828 | 1.889 | 18.513 | 0.997 |
| raw_lidar | size | low | 66 | 0.894 | 0.933 | 0.924 | 18.455 | 1.000 |
| raw_lidar | size | mid | 67 | 0.910 | 0.984 | 1.419 | 18.752 | 0.998 |
| raw_lidar | observation | high | 66 | 0.985 | 0.909 | 1.536 | 18.951 | 0.997 |
| raw_lidar | observation | low | 66 | 0.803 | 0.925 | 1.870 | 18.492 | 0.998 |
| raw_lidar | observation | mid | 67 | 0.896 | 0.917 | 1.145 | 18.680 | 0.999 |
| raw_lidar | manual_failure_label | 가림 | 11 | 1.000 | 0.818 | 0.638 | 17.857 | 0.998 |
| raw_lidar | manual_failure_label | 관측각·커버리지 | 17 | 1.000 | 1.000 | 1.398 | 18.539 | 0.999 |
| raw_lidar | manual_failure_label | 무텍스처 | 4 | 1.000 | 1.000 | 0.736 | 18.702 | 1.000 |
| raw_lidar | manual_failure_label | 복합(세장+관측각) | 1 | 1.000 | 1.000 | 3.186 | 20.287 | 1.000 |
| raw_lidar | manual_failure_label | 복합(소형+가림) | 4 | 1.000 | 1.000 | 2.780 | 17.264 | 0.986 |
| raw_lidar | manual_failure_label | 복합(소형+재질) | 4 | 1.000 | 1.000 | 0.684 | 18.143 | 1.000 |
| raw_lidar | manual_failure_label | 복합(스침각+가림) | 1 | 1.000 | 1.000 | 0.744 | 10.846 | 0.998 |
| raw_lidar | manual_failure_label | 복합(재질+가림) | 1 | 1.000 | 1.000 | 0.277 | 19.598 | 1.000 |
| raw_lidar | manual_failure_label | 복합(저조도+가림) | 1 | 1.000 | 1.000 | 1.631 | 18.444 | 1.000 |
| raw_acmp | complexity | high | 7 | 0.571 | 0.429 | 9.043 | 0.465 | 0.101 |
| raw_acmp | complexity | low | 51 | 0.255 | 0.255 | 1.429 | 2.353 | 0.239 |
| raw_acmp | complexity | mid | 6 | 0.500 | 0.333 | 4.077 | 0.868 | 0.186 |
| raw_acmp | size | high | 7 | 0.714 | 0.429 | 9.082 | 0.730 | 0.094 |
| raw_acmp | size | low | 32 | 0.281 | 0.281 | 8.248 | 1.231 | 0.145 |
| raw_acmp | size | mid | 25 | 0.240 | 0.240 | 0.000 | 2.583 | 0.433 |
| raw_acmp | observation | high | 10 | 0.500 | 0.500 | 2.948 | 79.062 | 0.843 |
| raw_acmp | observation | low | 30 | 0.233 | 0.200 | 0.000 | 0.978 | 0.177 |
| raw_acmp | observation | mid | 24 | 0.333 | 0.292 | 8.715 | 0.451 | 0.090 |
| raw_acmp | manual_failure_label | 가림 | 11 | 0.273 | 0.273 | 10.415 | 0.242 | 0.049 |
| raw_acmp | manual_failure_label | 관측각·커버리지 | 17 | 0.176 | 0.176 | 0.000 | 1.522 | 0.283 |
| raw_acmp | manual_failure_label | 무텍스처 | 4 | 0.250 | 0.250 | 5.629 | 3.717 | 0.122 |
| raw_acmp | manual_failure_label | 복합(세장+관측각) | 1 | 0.000 | 0.000 | none | 1.272 | 0.250 |
| raw_acmp | manual_failure_label | 복합(소형+가림) | 4 | 0.250 | 0.250 | 8.715 | 0.248 | 0.061 |
| raw_acmp | manual_failure_label | 복합(소형+재질) | 4 | 0.500 | 0.500 | 2.859 | 2.337 | 0.200 |
| raw_acmp | manual_failure_label | 복합(스침각+가림) | 1 | 0.000 | 0.000 | none | 0.167 | 0.042 |
| raw_acmp | manual_failure_label | 복합(재질+가림) | 1 | 0.000 | 0.000 | none | 0.110 | 0.027 |
| raw_acmp | manual_failure_label | 복합(저조도+가림) | 1 | 1.000 | 1.000 | 9.962 | 4.259 | 0.331 |

## 그림

- 계수 그림: `docs/figs/attr_outcome_regression_v1/coef_forest.png`
- 대표 건물 속성-결과 패널: `docs/figs/attr_outcome_regression_v1/representative_buildings.png`

## 관찰

- raw_dense: 속성+관측기하 사양에서 절대값 상위 속성 계수는 assembled:pt_density_m2_reg=2.00, assembled:label_proxy_frac_all=-1.01, val3dity_valid:local_plane_rms_m=-0.63.
- raw_lidar: 속성+관측기하 사양에서 절대값 상위 속성 계수는 assembled:label_proxy_frac_all=549.19, assembled:pt_density_m2_reg=-0.76, val3dity_valid:coverage_frac_reg=0.53.
- raw_acmp: 속성+관측기하 사양에서 절대값 상위 속성 계수는 val3dity_valid:pt_density_m2_reg=-8.92, val3dity_valid:label_proxy_frac_all=-6.56, val3dity_valid:coverage_frac_reg=6.33.
- 위 문장은 계수 크기 순서만 적은 관찰이다. 원인·채택·강등 판정은 포함하지 않는다.

## 산출 파일

- 회귀 입력 스냅샷: `docs/regression_input_snapshot.csv`
- 계수 전수: `docs/attr_outcome_regression_coefficients_v1.csv`
- 영향점 전수: `docs/attr_outcome_regression_diagnostics_v1.csv`
- 감도 전수: `docs/attr_outcome_regression_sensitivity_v1.csv`
- versions: `runs/20260706_regression_v1/versions.txt`
