# W_E5_C001_GS진단

> 재확인: 학습 0 · 레시피 0 · Roofer 0 · 판정 0. 기존 C001 GS 6런, raw 3, LiDAR, 참조 LoD2, val3dity 보고서, 기존 관측 스냅샷만 읽었다. CRS는 EPSG:25832.

## 데이터 의존성

- 브랜치·HEAD: `feat/p2-structure-learn` · `f73c1a331588d88afe55233e8fd0f9c585efa98e`.
- 한계: C001 18동 최악 블록, 2씨드, 영상 텍스처는 기존 수동/관측 스냅샷 기반 근사, ACMP는 정답이 아니라 이겨야 할 기준선이다.
- 정답 계열: 형태는 참조 LoD2, 거리 상한은 LiDAR. ACMP는 목표 막대와 메커니즘 단서로만 사용했다.
- 높이 프레임: raw-sparse/raw-acmp/GS는 참조 대비 -45.7 m, raw-dense/LiDAR는 0 m로 계산했다. 원본은 수정하지 않았다.
- 렌더 깊이: 학습 체크포인트와 RGB 렌더, readout TSDF/분류 LAS는 있으나 GS 렌더 깊이 래스터는 저장본을 확인하지 못했다. 평판화 위치는 `분류 LAS 점군 구조 + ACMP/raw-dense 점군 구조` 대체 프록시다.

## 입력 재고

| source_run | source_group | status | cityjson_path | pointcloud_path | z_shift_to_reference_m | missing_count |
|---|---|---|---|---|---|---|
| raw_sparse | raw_sparse | present | phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/cityjson/raw_sparse_roofer.city.json | phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/classified/raw_sparse_classified.laz | -45.7000 | 0 |
| raw_dense | raw_dense | present | phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/cityjson/dim_roofer.city.json | phases/p0-audit/data/work/w2/dim_v1_classified_z_minus0p174.laz | 0.0000 | 0 |
| raw_acmp | raw_acmp | present | phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813/cityjson/raw_acmp_roofer.city.json | phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813/classified/raw_acmp_classified.laz | -45.7000 | 0 |
| gs_sparse_r1 | gs_sparse | present | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_sparse_r1_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_sparse_r1/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| gs_sparse_r2 | gs_sparse | present | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_sparse_r2_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_sparse_r2/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| gs_dense_r1 | gs_dense | present | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_dense_r1_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_dense_r1/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| gs_dense_r2 | gs_dense | present | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_dense_r2_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_dense_r2/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| gs_acmp_r1 | gs_acmp | present | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_acmp_r1_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_acmp_r1/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| gs_acmp_r2 | gs_acmp | present | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_acmp_r2_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_acmp_r2/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| lidar | lidar | present | phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/cityjson/als_roofer.city.json | results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz | 0.0000 | 0 |
| reference | reference | present | phases/p0-audit/data/raw/lod2/*.gml |  | 0.0000 |  |

## 헤드라인 답

| metric | mean_delta_density | mean_delta_coverage | median_noise_gain_raw_minus_gs_m |
|---|---|---|---|
| GS-dense vs raw-dense | 34.8165 | -0.0769 | -0.6934 |

- GS 입력 개선/악화: GS-dense vs raw-dense의 `raw RMS - GS RMS` 중앙값은 -0.6934 m로 관찰됐다. 양수는 개선, 음수는 악화다.
- 영상 탓 vs 방법 탓: both_fail_or_invalid 2, both_have_success 9, common_texture_limit_proxy 1, gs_only_success 4, method_or_acmp_proxy_texture_unknown 2.
- 평판화 위치: gs_depth_or_gs_readout_proxy 5, not_built_no_flattening_localization 6, readout_roofer_proxy 6, structure_survived_proxy 1. 렌더 깊이 부재로 직접 인과가 아니라 프록시다.

## 공유 뿌리: 점군 진단

| source_run | n | median_density_pts_m2 | median_coverage_frac | median_ref_dist_rms_m | median_normal_mode_count | flat_single | multi_slope | single_slope | weak_or_sparse |
|---|---|---|---|---|---|---|---|---|---|
| raw_sparse | 18 | 0.0586 | 0.0148 | 2.6033 | 0.0000 | 0 | 7 | 1 | 10 |
| raw_dense | 18 | 3.1347 | 0.1483 | 1.1212 | 2.0000 | 0 | 9 | 1 | 8 |
| raw_acmp | 18 | 26.1737 | 0.6208 | 5.0380 | 2.0000 | 0 | 13 | 2 | 3 |
| gs_sparse_r1 | 18 | 1.8234 | 0.0388 | 5.0282 | 1.0000 | 0 | 6 | 6 | 6 |
| gs_sparse_r2 | 18 | 2.7070 | 0.0576 | 2.4516 | 2.0000 | 0 | 7 | 2 | 9 |
| gs_dense_r1 | 18 | 1.7641 | 0.0358 | 3.2399 | 1.0000 | 1 | 7 | 3 | 7 |
| gs_dense_r2 | 18 | 2.9489 | 0.0675 | 2.6476 | 1.0000 | 4 | 5 | 5 | 4 |
| gs_acmp_r1 | 18 | 2.8480 | 0.0484 | 6.3290 | 1.0000 | 0 | 7 | 5 | 6 |
| gs_acmp_r2 | 18 | 1.7521 | 0.0451 | 4.0698 | 2.0000 | 0 | 11 | 2 | 5 |
| lidar | 18 | 20.3097 | 1.0000 | 2.1970 | 2.0000 | 1 | 15 | 1 | 1 |

- 점군 행 단위: `docs/e5_c001_gsdiag_pointcloud_metrics.csv`.
- GS-x vs raw-x 짝 델타: `docs/e5_c001_gsdiag_pair_deltas.csv`.

## 영상층

| building_id | texture_class | texture_sufficient_proxy | n_views_nadir | recon_score_median | acmp_success | gs_success_count_clean | mechanism_bucket |
|---|---|---|---|---|---|---|---|
| DEBY_LOD2_108247349 | not_reviewed | unknown | 0.000000 | 71.823000 | false | 0 | both_fail_or_invalid |
| DEBY_LOD2_108247350 | texture_sufficient_proxy | true | 0.000000 | 67.515000 | true | 1 | both_have_success |
| DEBY_LOD2_108247351 | texture_poor | false | 0.000000 | 74.873000 | true | 2 | both_have_success |
| DEBY_LOD2_4907184 | not_reviewed | unknown | 1.420000 | 127.033000 | true | 2 | both_have_success |
| DEBY_LOD2_4907185 | not_reviewed | unknown | 0.650000 | 129.596000 | true | 6 | both_have_success |
| DEBY_LOD2_4907186 | not_reviewed | unknown | 0.000000 | 68.276000 | true | 6 | both_have_success |
| DEBY_LOD2_4907188 | not_reviewed | unknown | 0.000000 | 64.062000 | true | 0 | method_or_acmp_proxy_texture_unknown |
| DEBY_LOD2_4907194 | not_reviewed | unknown | 0.000000 | 51.146000 | true | 0 | method_or_acmp_proxy_texture_unknown |
| DEBY_LOD2_4907195 | not_reviewed | unknown | 0.000000 | 42.140000 | true | 6 | both_have_success |
| DEBY_LOD2_4907198 | not_reviewed | unknown | 0.090000 | 86.069000 | true | 6 | both_have_success |
| DEBY_LOD2_4907199 | texture_poor | false | 0.000000 | 84.618000 | false | 0 | common_texture_limit_proxy |
| DEBY_LOD2_4907202 | not_reviewed | unknown | 1.940000 | 84.473000 | true | 3 | both_have_success |
| DEBY_LOD2_4908168 | not_reviewed | unknown | 2.900000 | 160.781000 | true | 2 | both_have_success |
| DEBY_LOD2_4908178 | not_reviewed | unknown | 0.320000 | 63.723000 | false | 1 | gs_only_success |
| DEBY_LOD2_4908179 | not_reviewed | unknown | 0.000000 | 75.129000 | false | 0 | both_fail_or_invalid |
| DEBY_LOD2_60098 | not_reviewed | unknown | 0.000000 | 78.074000 | false | 5 | gs_only_success |
| DEBY_LOD2_8568391 | texture_poor | false | 1.020000 | 86.872000 | false | 1 | gs_only_success |
| DEBY_LOD2_8568392 | texture_poor | false | 2.250000 | 94.587000 | false | 1 | gs_only_success |

## 생성

- 생성 실패 원인 프록시: collapse_invalid_or_rms_tail 19, no_planes 17, no_points 30.
- 상세표: `docs/e5_c001_gsdiag_generation_failures.csv`.

## 품질

| building_id | source_run | model_shape_class | point_normal_structure | acmp_point_structure | raw_dense_point_structure | flattening_location_proxy |
|---|---|---|---|---|---|---|
| DEBY_LOD2_60098 | gs_dense_r1 | no_model | multi_slope | multi_slope | multi_slope | not_built_no_flattening_localization |
| DEBY_LOD2_60098 | gs_dense_r2 | flat_or_single_plane | multi_slope | multi_slope | multi_slope | readout_roofer_proxy |
| DEBY_LOD2_60098 | gs_acmp_r1 | flat_or_single_plane | multi_slope | multi_slope | multi_slope | readout_roofer_proxy |
| DEBY_LOD2_60098 | gs_acmp_r2 | flat_or_single_plane | multi_slope | multi_slope | multi_slope | readout_roofer_proxy |
| DEBY_LOD2_4908178 | gs_dense_r1 | flat_or_single_plane | weak_structure | multi_slope | weak_structure | gs_depth_or_gs_readout_proxy |
| DEBY_LOD2_4908178 | gs_dense_r2 | flat_or_single_plane | flat_single | multi_slope | weak_structure | gs_depth_or_gs_readout_proxy |
| DEBY_LOD2_4908178 | gs_acmp_r1 | no_model | single_slope | multi_slope | weak_structure | not_built_no_flattening_localization |
| DEBY_LOD2_4908178 | gs_acmp_r2 | multi_plane | multi_slope | multi_slope | weak_structure | structure_survived_proxy |
| DEBY_LOD2_4908168 | gs_dense_r1 | no_model | too_few_points | single_slope | single_slope | not_built_no_flattening_localization |
| DEBY_LOD2_4908168 | gs_dense_r2 | flat_or_single_plane | flat_single | single_slope | single_slope | gs_depth_or_gs_readout_proxy |
| DEBY_LOD2_4908168 | gs_acmp_r1 | flat_or_single_plane | weak_structure | single_slope | single_slope | gs_depth_or_gs_readout_proxy |
| DEBY_LOD2_4908168 | gs_acmp_r2 | no_model | too_few_points | single_slope | single_slope | not_built_no_flattening_localization |

- 모델 형태 지표: `docs/e5_c001_gsdiag_shape_metrics.csv`.
- 평판화 위치 프록시: `docs/e5_c001_gsdiag_flattening_location.csv`.

## 유효성

| source_run | category | buildings_with_category | error_instances |
|---|---|---|---|
| raw_sparse | valid | 18 | 0 |
| raw_dense | valid | 15 | 0 |
| raw_acmp | duplicate_degenerate | 1 | 2 |
| raw_acmp | valid | 17 | 0 |
| gs_sparse_r1 | face_orientation | 3 | 3 |
| gs_sparse_r1 | self_intersection | 1 | 15 |
| gs_sparse_r1 | valid | 14 | 0 |
| gs_sparse_r2 | duplicate_degenerate | 1 | 2 |
| gs_sparse_r2 | non_closed_shell | 1 | 2 |
| gs_sparse_r2 | valid | 16 | 0 |
| gs_dense_r1 | face_orientation | 1 | 1 |
| gs_dense_r1 | non_closed_shell | 1 | 2 |
| gs_dense_r1 | self_intersection | 1 | 12 |
| gs_dense_r1 | valid | 15 | 0 |
| gs_dense_r2 | face_orientation | 1 | 1 |
| gs_dense_r2 | non_closed_shell | 1 | 2 |
| gs_dense_r2 | valid | 16 | 0 |
| gs_acmp_r1 | duplicate_degenerate | 1 | 2 |
| gs_acmp_r1 | non_closed_shell | 2 | 4 |
| gs_acmp_r1 | valid | 15 | 0 |
| gs_acmp_r2 | non_closed_shell | 4 | 8 |
| gs_acmp_r2 | valid | 14 | 0 |
| lidar | non_closed_shell | 1 | 1 |
| lidar | valid | 14 | 0 |

## 조건·불안정성

- 조건 층화는 영상층 표의 텍스처/관측 열과 `docs/e5_c001_8way_strata_summary.csv`를 같이 읽는다.
- 씨드 불안정성은 `docs/experiments/pilots/e5_pilot/tables/e5_pilot_seed_pair_status.csv`의 r1/r2 flip과 생성 상세표의 `seed_flag`로 연결했다. 2씨드라 방향만 기록했다.

## 종합·라우팅

| question | observation | routing |
|---|---|---|
| GS가 자기 입력을 개선하나 | GS-dense vs raw-dense median/mean pair deltas | negative_noise_gain_or_mixed_density_coverage_observed |
| 영상 탓인가 방법 탓인가 | both_fail_or_invalid=2; both_have_success=9; common_texture_limit_proxy=1; gs_only_success=4; method_or_acmp_proxy_texture_unknown=2 | proxy_video_layer_only |
| 평판화는 깊이인가 readout인가 | gs_depth_or_gs_readout_proxy=5; not_built_no_flattening_localization=6; readout_roofer_proxy=6; structure_survived_proxy=1 | render_depth_absent_proxy |
| 생성 실패 뿌리 | collapse_invalid_or_rms_tail=19; no_planes=17; no_points=30 | root_pointcloud_status_linked |
| 유효성 오류 | duplicate_degenerate=3; face_orientation=5; non_closed_shell=9; self_intersection=2 | val3dity_report_reparsed |

## 인용

- `사전등록서_본비교실험E5·기준레시피_v1_20260706.md` §4(측정)·§5(생성/유효성/품질 축)·§10(규약).
- `기준문서_방법론·모집단·비교설계_v1.md` 부록 A/D.
- `docs/W_E5_C001_8way.md`, `docs/experiments/pilots/e5_pilot/manifests/e5_baselines_199_manifest.json`.
- P0 텍스처/유효성 진단: `phases/p0-audit/docs/G1_package/t9_failure_surface_cause_building_metrics.csv`, `phases/p0-audit/docs/G1_package/t11_survivor_texture_refine_building_metrics.csv`, `phases/p0-audit/docs/G1_package/t13_validity_error_breakdown_type_by_input.csv`.
- 요청문에 적힌 `docs/W_E5_C001_8way_분석·199판단_20260707.md`는 현재 checkout에서 발견하지 못했다. 잠금본과 어긋나는 경우 잠금본을 우선한다.

## 산출물

- 보고서: `docs/W_E5_C001_GS진단.md`.
- 표: `docs/e5_c001_gsdiag_pointcloud_metrics.csv`, `docs/e5_c001_gsdiag_pointcloud_source_summary.csv`, `docs/e5_c001_gsdiag_pair_deltas.csv`, `docs/e5_c001_gsdiag_video_layer.csv`, `docs/e5_c001_gsdiag_generation_failures.csv`, `docs/e5_c001_gsdiag_shape_metrics.csv`, `docs/e5_c001_gsdiag_flattening_location.csv`, `docs/e5_c001_gsdiag_validity_errors.csv`, `docs/e5_c001_gsdiag_validity_error_summary.csv`, `docs/e5_c001_gsdiag_routing.csv`, `docs/e5_c001_gsdiag_headline_summary.csv`.
- 그림: `docs/figs/e5_c001_gsdiag/`.
- `docs/figs/e5_c001_gsdiag/pair_delta_gs_vs_raw.png`
- `docs/figs/e5_c001_gsdiag/texture_success_heatmap.png`
- `docs/figs/e5_c001_gsdiag/normal_distribution_flat_cases.png`
- `docs/figs/e5_c001_gsdiag/shape_similarity_scatter.png`
- `docs/figs/e5_c001_gsdiag/flattening_location_cases.png`
- `docs/figs/e5_c001_gsdiag/density_coverage_summary.png`
- 버전: `phases/p2-gsjso/runs/20260707_e5_c001_gsdiag/versions.txt`.

## 관찰

- 데이터는 GS-dense의 거리·형태 축이 raw-dense보다 불리하게 나온 사례가 섞여 있고, ACMP가 같은 블록에서 더 넓은 커버리지와 전파 이점을 보이는 패턴으로 관찰된다.
- 평판화는 일부 사례에서 모델만 단순화된 readout/Roofer 프록시와, 점군 단계부터 구조가 약한 GS 깊이/readout 프록시가 함께 관찰된다. 이는 판정이 아니라 다음 라우팅을 위한 관찰이다.
