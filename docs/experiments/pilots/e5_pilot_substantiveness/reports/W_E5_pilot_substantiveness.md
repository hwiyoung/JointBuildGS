# E5 파일럿 실질성 분류

> 판정 금지. 재학습 0 · 레시피 변경 0 · Roofer 변경 0. 기존 6런 `gs_e5_C001_{sparse,dense,acmp}_{r1,r2}` 산출만 읽었다. CRS는 EPSG:25832.

## 시작 전 확인

- 브랜치·HEAD: `feat/p2-structure-learn` · `361712bf89205f689cc3a5cb7bfb35326d2e230d`.
- 입력 보고서·표: `docs/experiments/pilots/e5_pilot/reports/W_E5_pilot_gate.md`, `docs/experiments/pilots/e5_pilot/tables/e5_pilot_seed_pair_status.csv`.
- 조립 출력: `phases/p0-audit/runs/e5p_gate_20260707_C001/`.
- 점군화·지문: `phases/p2-gsjso/runs/e5_c001/e5p_train_20260707_C001/`.
- 참조 지붕 구조: LoD2 참조 CityGML의 RoofSurface 수·형상. W_D6 형상 교정본을 준용했고, 4906969는 단차 평지붕이며 D6 작업동의 곡면 지붕은 0동으로 기록한다.

## 잣대

- 1차 축: GS 지붕면 수와 참조 RoofSurface 수를 비교했다. 0이면 결손, 참조보다 작으면 과병합, 같으면 구조 일치, 크면 과분할로 적었다.
- 분류표는 C001 18동 전수 회계다. 성공 수는 `has_lod22`이고, 결손은 지붕면 0인 미조립 행까지 포함한다.
- 2차 축: `rf_rmse_lod22` 분포를 봤다. 적합 붕괴는 전체 GS run_1 성공 61건의 Tukey 상단 울타리로 표시했다.
- RMSE 분포값: Q1 0.944 m · 중앙값 2.283 m · Q3 4.497 m · 꼬리선 9.826 m.
- 그림에는 LDBV LoD2 1 m와 P0 4907019 껍데기 31 m를 앵커선으로 함께 표시했다.
- 유효성(val3dity)은 실질성 기준이 아니므로 별도 열로만 병기했다.
- 정밀 completeness/correctness 매칭은 전수 실험으로 이월한다. 파일럿은 지붕면 수 대 참조와 RMSE 분포로 근사했다.

## 분류표

| 씨앗 | 씨드 | 성공 수 | 결손 | 과병합 | 구조 일치 | 과분할 | 적합 붕괴(rmse 꼬리) | 클린 | val3dity 유효 |
|---|---|---|---|---|---|---|---|---|---|
| sparse | r1 | 9 | 9 | 2 | 1 | 6 | 3 | 1 | 14 |
| sparse | r2 | 11 | 7 | 2 | 4 | 5 | 0 | 4 | 16 |
| dense | r1 | 8 | 10 | 1 | 3 | 4 | 1 | 3 | 15 |
| dense | r2 | 13 | 5 | 1 | 6 | 6 | 0 | 6 | 16 |
| acmp | r1 | 9 | 9 | 1 | 3 | 5 | 2 | 2 | 15 |
| acmp | r2 | 11 | 7 | 1 | 2 | 8 | 2 | 2 | 14 |

## 씨앗별 짝 대비

| 씨앗 | 짝 기준 | 기준 has_lod22 | GS r1 has_lod22 | GS r1 클린 | GS r2 has_lod22 | GS r2 클린 |
|---|---|---|---|---|---|---|
| sparse | raw-sparse | 2/18 | 9/18 | 1/18 | 11/18 | 4/18 |
| dense | raw-dense(w2_1 DIM) | 10/18 | 8/18 | 3/18 | 13/18 | 6/18 |
| acmp | raw-ACMP | 12/18 | 9/18 | 2/18 | 11/18 | 2/18 |

## 그림

- 지붕면 수 산점도: `docs/figs/e5_pilot/subst/scatter_roofplanes_by_seed.png`.
- RMSE 분포: `docs/figs/e5_pilot/subst/rmse_hist_by_seed.png`.
- 결손 전수 그림: `docs/figs/e5_pilot/subst/pathology_all_shell.png`.
- 과분할 전수 그림: `docs/figs/e5_pilot/subst/pathology_all_overseg.png`.

## 정성 패널 선정

| 유형 | 선정 규칙 | 씨앗 | 씨드 | building_id | ref_roof_planes | gs_roof_planes | rf_rmse_lod22 | primary_label | clean | figure |
|---|---|---|---|---|---|---|---|---|---|---|
| 구조 일치 대표 | 클린 중 RMSE 중앙값에 가장 가까움 | sparse | r2 | DEBY_LOD2_108247351 | 1 | 1 | 2.551575 | 구조 일치 | True | docs/figs/e5_pilot/subst/panel_typical_clean_sparse_r2_DEBY_LOD2_108247351.png |
| 무텍스처 복구 | 8568391·8568392 중 has_lod22 후 RMSE 낮은 행 | sparse | r1 | DEBY_LOD2_8568391 | 1 | 2 | 12.204517 | 과분할 | False | docs/figs/e5_pilot/subst/panel_textureless_sparse_r1_DEBY_LOD2_8568391.png |
| 씨드 변동 | r1/r2 has_lod22 flip 중 building_id 사전순 첫 행 | sparse | r1 | DEBY_LOD2_108247350 | 1 | 0 |  | 결손 | False | docs/figs/e5_pilot/subst/panel_seed_flip_sparse_DEBY_LOD2_108247350.png |
| 구조 일치 대표 | 클린 중 RMSE 중앙값에 가장 가까움 | dense | r2 | DEBY_LOD2_60098 | 2 | 2 | 0.933127 | 구조 일치 | True | docs/figs/e5_pilot/subst/panel_typical_clean_dense_r2_DEBY_LOD2_60098.png |
| 무텍스처 복구 | 8568391·8568392 중 has_lod22 후 RMSE 낮은 행 | dense | r2 | DEBY_LOD2_8568391 | 1 | 1 | 0.007875 | 구조 일치 | True | docs/figs/e5_pilot/subst/panel_textureless_dense_r2_DEBY_LOD2_8568391.png |
| 씨드 변동 | r1/r2 has_lod22 flip 중 building_id 사전순 첫 행 | dense | r1 | DEBY_LOD2_108247350 | 1 | 0 |  | 결손 | False | docs/figs/e5_pilot/subst/panel_seed_flip_dense_DEBY_LOD2_108247350.png |
| 구조 일치 대표 | 클린 중 RMSE 중앙값에 가장 가까움 | acmp | r2 | DEBY_LOD2_4907186 | 2 | 2 | 2.357641 | 구조 일치 | True | docs/figs/e5_pilot/subst/panel_typical_clean_acmp_r2_DEBY_LOD2_4907186.png |
| 씨드 변동 | r1/r2 has_lod22 flip 중 building_id 사전순 첫 행 | acmp | r1 | DEBY_LOD2_4907194 | 2 | 0 |  | 결손 | False | docs/figs/e5_pilot/subst/panel_seed_flip_acmp_DEBY_LOD2_4907194.png |
| ACMP 회귀 | 지정 ID 108247350·108247351 중 GS 미조립 행 | acmp | r1 | DEBY_LOD2_108247350 | 1 | 0 |  | 결손 | False | docs/figs/e5_pilot/subst/panel_acmp_regression_r1_DEBY_LOD2_108247350.png |
| ACMP 회귀 | 지정 ID 108247350·108247351 중 GS 미조립 행 | acmp | r1 | DEBY_LOD2_108247351 | 1 | 0 |  | 결손 | False | docs/figs/e5_pilot/subst/panel_acmp_regression_r1_DEBY_LOD2_108247351.png |

## 산출 표

- 전수 세부표: `docs/e5_pilot_substantiveness_detail.csv`.
- 요약표: `docs/e5_pilot_substantiveness_summary.csv`.
- 클린 재집계: `docs/e5_pilot_substantiveness_pair_clean.csv`.
- 패널 선정표: `docs/e5_pilot_substantiveness_panel_selection.csv`.
- 실행 지문: `phases/p2-gsjso/runs/e5_c001/20260707_e5_pilot_subst/versions.txt`.

## 관찰

- sparse: 성공 20/36 · 결손 16/36 · 과분할 11/36 · 클린 5/36 / dense: 성공 21/36 · 결손 15/36 · 과분할 10/36 · 클린 9/36 / acmp: 성공 20/36 · 결손 16/36 · 과분할 13/36 · 클린 4/36. 각 수치는 씨앗별 36행 기준이다.
- 위 수치와 그림은 판정 재료이며, 게이트 판단 문구는 쓰지 않는다.
