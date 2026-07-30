# R2 C001 정성 패널·roof completeness·Hausdorff 정의

- 측정일: 2026-07-18
- `learning_runs_started=0`
- `new_inference_runs=0`
- 기존 CityJSON·LoD2 채점 산출물 읽기 전용; 학습·재구성·Roofer 조립 없음.

## 산출 행 수

- `qs_rescore_scores.csv`: 2813행, `roof_completeness` 전 행 기재.
- dense-success 모집단: 10동.
- top-view panel: 40행; 열별 {'reference': 10, 'dense_w2_1': 10, 'gs_fixed': 10, 'gs_oracle': 10}.
- Hausdorff spot 재계산: 12행.

## roof_completeness 정의

`roof_completeness = area(union(model roof XY) ∩ union(reference roof XY)) / area(union(reference roof XY))`

- 계산 코드 경로: `scripts/quality_score/p2_gsjso/qs_rescore_completeness_panel.py`의 `roof_completeness_xy()`.
- 지붕면은 `scripts/e5_c001/p2_gsjso/e5_c001_8way.py`의 `parse_lod2_roofs()`·`parse_cityjson_roofs()`가 생성한 XY polygon을 사용.
- 모델 지붕면이 없으면 0.0, 참조 자기 대조는 1.0.
- 기존 면 개수 기반 `completeness` 필드는 변경하지 않음.
- ISPRS completeness 계열 출처: https://www.isprs.org/resources/datasets/benchmarks/IndoorModeling/results.aspx
- 접속일: 2026-07-18. 이번 구현은 roof XY projection, buffer b=0 특수화.

## roof_hausdorff_m 코드 정의

- 코드 경로: `scripts/e5_c001/p2_gsjso/e5_c001_8way.py`의 `reference_distance()`·`sample_polygon_points()`.
- 모델 지붕면 XY 내부를 0.50 m 격자로 표본화; 면당 최대 1,200표본.
- 각 모델 표본에서 참조 지붕면까지의 수직 z 차이를 계산.
- 같은 XY를 덮는 참조면이 여러 개면 모델 z와 절대차가 가장 작은 참조 z를 사용.
- 덮는 참조면이 없으면 XY 최단거리 참조면을 사용.
- `roof_hausdorff_m = max(abs(z_model - z_reference))`.
- 방향은 모델→참조 단방향이며 참조→모델 표본화와 XY 거리 성분은 없음.

## 3동 동일 코드 경로 재계산

| building_id | panel_column | stored_roof_hausdorff_m | recomputed_roof_hausdorff_m | delta_roof_hausdorff_m | recomputed_roof_distance_samples |
| --- | --- | --- | --- | --- | --- |
| DEBY_LOD2_4907184 | reference | 0.000000000 | 0.000000000 | 0.000000000 | 1353 |
| DEBY_LOD2_4907184 | dense_w2_1 | 2.638333513 | 2.638333513 | -0.000000000 | 1348 |
| DEBY_LOD2_4907184 | gs_fixed | 2.651652763 | 2.651652763 | 0.000000000 | 1348 |
| DEBY_LOD2_4907184 | gs_oracle | 0.530460782 | 0.530460782 | 0.000000000 | 1347 |
| DEBY_LOD2_4908168 | reference | 0.000000000 | 0.000000000 | 0.000000000 | 114 |
| DEBY_LOD2_4908168 | dense_w2_1 | 0.442979418 | 0.442979418 | 0.000000000 | 114 |
| DEBY_LOD2_4908168 | gs_fixed | 3.241456064 | 3.241456064 | -0.000000000 | 114 |
| DEBY_LOD2_4908168 | gs_oracle | 0.543754976 | 0.543754976 | -0.000000000 | 24 |
| DEBY_LOD2_4907188 | reference | 0.000000000 | 0.000000000 | 0.000000000 | 662 |
| DEBY_LOD2_4907188 | dense_w2_1 | 4.138715144 | 4.138715144 | -0.000000000 | 664 |
| DEBY_LOD2_4907188 | gs_fixed | 19.555005138 | 19.555005138 | 0.000000000 | 664 |
| DEBY_LOD2_4907188 | gs_oracle | 3.954383901 | 3.954383901 | -0.000000000 | 664 |

## top-view 패널

- `docs/figs/qs_rescore/qs_rescore_topview_10x4.png`
- 열: reference | dense_w2_1 | gs_fixed | gs_oracle.
- 각 건물 행의 네 셀은 동일 XY bounds를 사용.
- 각 셀 주석: 지붕면 수, roof RMS, roof_completeness.

## 고정 선택 주소

- dense: `canonical_dense_w2_1`
- GS fixed: `e5p_405_repair_20260709_C001:e5p_3b_s1_20260708_C001:base:gs_e5_C001_s1_acmp_r1:run_1`
- GS oracle: `docs/qs_rescore_oracle_audit.csv`의 기존 `per_building_oracle_upper_bound_not_fixed_condition` 주소.

판정·게이트 해석 없음.
