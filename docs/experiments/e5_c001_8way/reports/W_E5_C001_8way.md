# E5 C001 8-way 참조 매칭

> 재확인: 신규 학습 0 · 레시피 변경 0 · Roofer 변경 0 · 판정 문구 0. 기존 C001 6런과 기준선 조립 산출만 읽었다. CRS는 EPSG:25832.

## 시작 전 확인

- 브랜치·HEAD: `feat/p2-structure-learn` · `4c3c71e8ed6fd289076461e6e7bfd5479a73cafb`.
- 기존 게이트 보고: `docs/experiments/e5_pilot/reports/W_E5_pilot_gate.md`, `docs/W_E5_pilot_gate_검수·판정회부_20260707.md`.
- GS 점군화·지문: `phases/p2-gsjso/runs/e5p_train_20260707_C001/`.
- GS 조립 출력: `phases/p0-audit/runs/e5p_gate_20260707_C001/`.
- 새 학습·새 파라미터·새 Roofer 조립은 하지 않았다.
- 기준문서 파일 머리표기는 v1.25(2026-07-06)다. 발주문은 v1.27을 언급하지만, repo의 잠금본 사전등록서와 현재 기준문서 부록 A/D를 우선 인용했다.

## 입력 재고

| source_run | source_group | status | status_path | cityjson_path | pointcloud_path | z_shift_to_reference_m | missing_count |
|---|---|---|---|---|---|---|---|
| raw_sparse | raw_sparse | present | phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/building_reconstruction_status.csv | phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/cityjson/raw_sparse_roofer.city.json | phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/classified/raw_sparse_classified.laz | -45.7000 | 0 |
| raw_dense | raw_dense | present | phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv | phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/cityjson/dim_roofer.city.json | phases/p0-audit/data/work/w2/dim_v1_classified_z_minus0p174.laz | 0.0000 | 0 |
| raw_acmp | raw_acmp | present | phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813/building_reconstruction_status.csv | phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813/cityjson/raw_acmp_roofer.city.json | phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813/classified/raw_acmp_classified.laz | -45.7000 | 0 |
| gs_sparse_r1 | gs_sparse | present | phases/p0-audit/runs/e5p_gate_20260707_C001/building_reconstruction_status.csv | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_sparse_r1_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_sparse_r1/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| gs_sparse_r2 | gs_sparse | present | phases/p0-audit/runs/e5p_gate_20260707_C001/building_reconstruction_status.csv | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_sparse_r2_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_sparse_r2/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| gs_dense_r1 | gs_dense | present | phases/p0-audit/runs/e5p_gate_20260707_C001/building_reconstruction_status.csv | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_dense_r1_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_dense_r1/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| gs_dense_r2 | gs_dense | present | phases/p0-audit/runs/e5p_gate_20260707_C001/building_reconstruction_status.csv | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_dense_r2_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_dense_r2/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| gs_acmp_r1 | gs_acmp | present | phases/p0-audit/runs/e5p_gate_20260707_C001/building_reconstruction_status.csv | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_acmp_r1_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_acmp_r1/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| gs_acmp_r2 | gs_acmp | present | phases/p0-audit/runs/e5p_gate_20260707_C001/building_reconstruction_status.csv | phases/p0-audit/runs/e5p_gate_20260707_C001/cityjson/gs_e5_C001_acmp_r2_run_1.city.json | phases/p0-audit/runs/e5p_gate_20260707_C001/roofer/gs_e5_C001_acmp_r2/run_1/{bid}_run_1_classified.las | -45.7000 | 0 |
| lidar | lidar | present | phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv | phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/cityjson/als_roofer.city.json | results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz | 0.0000 | 0 |
| reference | reference | present |  | phases/p0-audit/data/raw/lod2/*.gml |  | 0.0000 |  |

## 참조 매칭 방법

- 참조 지붕 구조는 LoD2 CityGML의 RoofSurface 수와 형상이다. W_D6 형상 교정본의 원칙을 준용했다.
- completeness/correctness 매칭: 수평 중첩 0.50 m2 이상, IoU 0.02 이상, 겹친 영역 높이 차이 중앙값 5.0 m 이하인 후보를 점수순으로 1:1 매칭했다.
- 참조거리 RMS/Hausdorff: 매칭 성패와 별도로 조립 지붕면 전체를 0.5 m 간격으로 샘플링하고, 같은 수평 위치의 참조 지붕면까지 높이 차이를 계산했다. 자기 점 RMSE가 아니다.
- 높이 프레임: raw-sparse·raw-acmp·GS 조립 CityJSON은 참조거리 계산에서 -45.7 m를 적용했다. raw-dense(MVS)와 LiDAR는 0 m다. 원본 산출물은 수정하지 않았다.
- 껍데기 3분할 규칙: CityJSON에 지붕면이 있으면 무효 모델이어도 면수는 센다. `미조립` / `지붕면0 성공` / `무효·붕괴` / `조립`은 별도 열로 낸다.
- `무효·붕괴`는 val3dity 무효 또는 참조거리 RMS의 Tukey 꼬리다. 이 규칙으로 4908178 같은 그림상 붕괴와 면수 계산을 동시에 보존한다.

## 8-way 정량 요약

| source_run | n | has_lod22 | val3dity_valid | 미조립 | 지붕면0 성공 | 무효·붕괴 | 조립 | mean_completeness | mean_correctness | median_ref_rms_m |
|---|---|---|---|---|---|---|---|---|---|---|
| raw_sparse | 18 | 2 | 18 | 16 | 0 | 0 | 2 | 0.0556 | 1.0000 | 1.8555 |
| raw_dense | 18 | 10 | 15 | 8 | 0 | 0 | 10 | 0.4583 | 0.7833 | 0.9896 |
| raw_acmp | 18 | 12 | 17 | 6 | 0 | 1 | 11 | 0.5556 | 0.4794 | 2.1467 |
| gs_sparse_r1 | 18 | 9 | 14 | 9 | 0 | 4 | 5 | 0.1528 | 0.3651 | 6.8284 |
| gs_sparse_r2 | 18 | 11 | 16 | 7 | 0 | 2 | 9 | 0.2361 | 0.5668 | 6.8449 |
| gs_dense_r1 | 18 | 8 | 15 | 10 | 0 | 3 | 5 | 0.1250 | 0.4250 | 7.1227 |
| gs_dense_r2 | 18 | 13 | 16 | 5 | 0 | 3 | 10 | 0.3472 | 0.6209 | 3.9967 |
| gs_acmp_r1 | 18 | 9 | 15 | 9 | 0 | 3 | 6 | 0.2361 | 0.5503 | 4.6174 |
| gs_acmp_r2 | 18 | 11 | 14 | 7 | 0 | 4 | 7 | 0.2639 | 0.5331 | 5.9575 |
| lidar | 18 | 15 | 14 | 3 | 0 | 1 | 14 | 0.8333 | 0.7137 | 0.2512 |
| reference | 18 | 18 | 18 | 0 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0.0000 |

## Correction gain

- 폭 정의: GS-x minus raw-x for completeness/correctness, raw RMS minus GS RMS for 참조거리(양수면 참조 쪽으로 가까워짐).

| arm | replicate | n | sum_delta_has_lod22 | mean_delta_completeness | mean_delta_correctness | median_ref_rms_gain_m |
|---|---|---|---|---|---|---|
| acmp | r1 | 18 | -3 | -0.3194 | -0.0571 | -2.3631 |
| acmp | r2 | 18 | -1 | -0.2917 | 0.0124 | -3.9968 |
| dense | r1 | 18 | -2 | -0.3333 | -0.3000 | -4.5627 |
| dense | r2 | 18 | 3 | -0.1111 | -0.1762 | -1.9596 |
| sparse | r1 | 18 | 7 | 0.0972 | -0.8572 | -5.8390 |
| sparse | r2 | 18 | 9 | 0.1806 | -0.3824 | 0.0108 |

## 층화 렌즈

- 복잡도·크기·관측 렌즈는 `docs/regression_input_snapshot.csv`의 C001 행을 재사용했다.
- 텍스처·라벨 렌즈는 `docs/manual_review_judgments.csv`가 있는 동만 세부 라벨을 쓰고, 나머지는 `not_reviewed` 또는 `none`으로 남겼다.
- 전체 층화 요약표: `docs/e5_c001_8way_strata_summary.csv`.

## 그림

- 건물당 그림은 18동 전수다. 8개 소스 그룹 중 GS 세 그룹은 r1/r2를 내부 칸으로 나눠 표시하므로 그림은 11칸으로 보인다.
- completeness/correctness 요약: `docs/figs/e5_c001_8way/summary_completeness_correctness.png`.
- 참조거리 요약: `docs/figs/e5_c001_8way/summary_ref_distance.png`.
- 건물별 그림 디렉터리: `docs/figs/e5_c001_8way/`.

- `docs/figs/e5_c001_8way/8way_108247349.png`
- `docs/figs/e5_c001_8way/8way_108247350.png`
- `docs/figs/e5_c001_8way/8way_108247351.png`
- `docs/figs/e5_c001_8way/8way_4907184.png`
- `docs/figs/e5_c001_8way/8way_4907185.png`
- `docs/figs/e5_c001_8way/8way_4907186.png`
- `docs/figs/e5_c001_8way/8way_4907188.png`
- `docs/figs/e5_c001_8way/8way_4907194.png`
- `docs/figs/e5_c001_8way/8way_4907195.png`
- `docs/figs/e5_c001_8way/8way_4907198.png`
- `docs/figs/e5_c001_8way/8way_4907199.png`
- `docs/figs/e5_c001_8way/8way_4907202.png`
- `docs/figs/e5_c001_8way/8way_4908168.png`
- `docs/figs/e5_c001_8way/8way_4908178.png`
- `docs/figs/e5_c001_8way/8way_4908179.png`
- `docs/figs/e5_c001_8way/8way_60098.png`
- `docs/figs/e5_c001_8way/8way_8568391.png`
- `docs/figs/e5_c001_8way/8way_8568392.png`

## 산출 표

- 원자료 행 단위: `docs/e5_c001_8way_metrics.csv`.
- 소스 요약: `docs/e5_c001_8way_source_summary.csv`.
- correction gain 세부: `docs/e5_c001_8way_correction_gain.csv`.
- correction gain 요약: `docs/e5_c001_8way_correction_gain_summary.csv`.
- 재고표: `docs/e5_c001_8way_inventory.csv`.
- 실행 지문: `phases/p2-gsjso/runs/20260707_e5_c001_8way/versions.txt`.

## 관찰

- gs_sparse_r1: C 0.1528 · R 0.3651 · RMS중앙 6.8284m / gs_sparse_r2: C 0.2361 · R 0.5668 · RMS중앙 6.8449m / gs_dense_r1: C 0.1250 · R 0.4250 · RMS중앙 7.1227m / gs_dense_r2: C 0.3472 · R 0.6209 · RMS중앙 3.9967m / gs_acmp_r1: C 0.2361 · R 0.5503 · RMS중앙 4.6174m / gs_acmp_r2: C 0.2639 · R 0.5331 · RMS중앙 5.9575m. 위 문장은 수치 관찰이며 게이트 판정이 아니다.
