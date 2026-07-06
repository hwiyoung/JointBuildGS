# W pointcloud attributes v1

> 재구성/재학습 없음. 이미지-투영 불사용. 수치와 관찰만 기록한다.

## 입력·규약

- 모집단: `docs/population_aux_v4.csv`의 199동 전수, arm 3종 = raw_dense(DIM) · raw_acmp · raw_lidar(상한).
- Footprint: `phases/p0-audit/data/work/w2/footprints_scene_aoi.gpkg` (EPSG:25832, 199 features).
- Status 대조: `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv` (fallback_canonical_w2_1_docs_copy_missing).
- 기존 클립: `phases/p0-audit/runs/mob_eval/raw_{dense,acmp,lidar}/<ID>_orig_classified.las`.
- ACMP 결측 fallback: `results/tum_transfer/mob_analysis/p0c_step2/acmp_classified.laz`에서 footprint 내부를 읽고 Z에 +48.0 m를 더해 ellip-unified raw arm 이력에 맞췄다. fallback은 CSV의 `clip_source`에 표시했다.
- LoD2 지붕면 Z는 정표고로 읽고, ③④⑤의 점-참조 높이 비교에서만 +48.165 m를 더했다.
- 채택값: grid=0.5 m, local plane radius=0.75 m, M3C2 normal/projection radius=1.0/0.75 m, 부유점 여유=3.0 m, 라벨 프록시=참조 지붕高-1.0 m 위 ground(2).

## 클립 출처

| arm | source | n_rows |
|---|---|---:|
| raw_dense | existing_mob_eval_clip | 50 |
| raw_dense | missing_clip | 149 |
| raw_acmp | existing_mob_eval_clip | 68 |
| raw_acmp | fallback_fused_acmp_footprint_clip | 131 |
| raw_lidar | existing_mob_eval_clip | 136 |
| raw_lidar | missing_clip | 63 |

## 축별·arm별 분포

| 축 | arm | n | median | IQR |
|---|---|---:|---:|---:|
| 밀도 pt/m2 | raw_dense | 29 | 8.4519 | 2.493–41.95 |
| 밀도 pt/m2 | raw_acmp | 198 | 77.2229 | 5.991–242.8 |
| 밀도 pt/m2 | raw_lidar | 136 | 18.5148 | 16.05–19.78 |
| 완전성 coverage | raw_dense | 29 | 0.3951 | 0.1333–0.8358 |
| 완전성 coverage | raw_acmp | 198 | 0.8620 | 0.3569–1 |
| 완전성 coverage | raw_lidar | 136 | 0.9982 | 0.9934–1 |
| 노이즈 local RMS m | raw_dense | 22 | 0.1402 | 0.07986–0.1769 |
| 노이즈 local RMS m | raw_acmp | 155 | 0.1771 | 0.151–0.2053 |
| 노이즈 local RMS m | raw_lidar | 136 | 0.1415 | 0.1109–0.163 |
| M3C2 RMS m | raw_dense | 22 | 1.2944 | 0.7119–2.282 |
| M3C2 RMS m | raw_acmp | 103 | 1.8822 | 1.464–2.267 |
| M3C2 RMS m | raw_lidar | 0 | none | none |
| 부유점 fraction | raw_dense | 29 | 0.0000 | 0–0.1163 |
| 부유점 fraction | raw_acmp | 198 | 0.0052 | 0.000851–0.124 |
| 부유점 fraction | raw_lidar | 136 | 0.0002 | 0–0.01777 |
| 라벨 프록시 fraction | raw_dense | 29 | 0.0000 | 0–0.25 |
| 라벨 프록시 fraction | raw_acmp | 198 | 0.0000 | 0–0.01748 |
| 라벨 프록시 fraction | raw_lidar | 136 | 0.0000 | 0–0 |

## 그림

- Arm 대조 분포: `docs/figs/pointcloud_attributes_v1/arm_distribution.png`
- ALS 대비 산점: `docs/figs/pointcloud_attributes_v1/als_scatter.png`

## 관찰

- 밀도: median raw_dense=8.4519, raw_acmp=77.2229, raw_lidar=18.5148.
- 0.5 m 격자 점유율: median raw_dense=0.3951, raw_acmp=0.8620, raw_lidar=0.9982.
- 국소 평면 RMS: median raw_dense=0.1402, raw_acmp=0.1771, raw_lidar=0.1415.
- 부유점 비율: median raw_dense=0.0000, raw_acmp=0.0052, raw_lidar=0.0002.
- 라벨 프록시 비율: median raw_dense=0.0000, raw_acmp=0.0000, raw_lidar=0.0000.
- ref_invalid 플래그가 켜진 건물: DEBY_LOD2_104586480, DEBY_LOD2_42364663.
- missing_clip 행: raw_dense=149, raw_acmp=0, raw_lidar=63.

## 판정 필요 지점

- 부유점 여유 3 m를 유지할지, arm별 z-noise를 반영해 조정할지.
- 라벨 프록시를 전체 점 대비 비율로 둘지 ground(2) 내부 비율로 둘지.
- `none` 처리 행을 회귀에서 결측으로 둘지, arm 결측 자체를 설명변수로 둘지.
- 회귀 사양: 199동 전수 분모를 유지하되 분석 단계에서 층화·제외·ref_invalid 처리 방식을 정할지.

---

# W pointcloud attributes v1.1

> 재구성/재학습 없음. 이미지-투영 불사용. 수치와 관찰만 기록한다. CRS는 EPSG:25832.

## v1.1 입력·높이 기준

- 기준문서 확인: 루트 기준문서 v1.14 (2026-07-05). §1.6의 확정값은 ζ=45.7 m, QA 유효값은 45.760 m이다.
- v1의 +48.0은 `phases/p2-gsjso/scripts/tum_mob_raw_to_npz.py`와 `docs/W_pointcloud_attributes.md`의 ACMP/LiDAR raw-arm 관행값이다. v1.1에서는 orthometric ACMP/ALS에 +45.760 m를 썼다.
- v1의 +48.165는 `phases/p2-gsjso/scripts/pointcloud_attributes_v1.py`의 `GEOID_MED_M`으로, 참조 LoD2 지붕 Z를 raw-arm 높이와 비교할 때만 더했던 값이다.
- 기존 mob_eval raw_acmp/raw_lidar 클립은 ellip-unified 이력의 기존 클립이며, 생성 이력은 orthometric +48.000 m이다. v1.1 metric 계산에서는 이 행들을 -2.240 m 평행이동해 +45.760 m 기준에 맞췄다.
- raw_dense는 기존 DIM ellipsoid/local+604 이력을 as-is로 두고, 참조 LoD2와의 비교 상수만 +45.760 m로 맞췄다.

## v1.1 클립 출처

| arm | source | n_rows |
|---|---|---:|
| raw_dense | existing_mob_eval_clip | 50 |
| raw_dense | fallback_dim_footprint_clip | 149 |
| raw_acmp | existing_mob_eval_clip | 68 |
| raw_acmp | fallback_fused_acmp_footprint_clip | 131 |
| raw_lidar | existing_mob_eval_clip | 136 |
| raw_lidar | fallback_als_footprint_clip | 63 |

## v1.1 축별·arm별 분포

| 축 | arm | n | median | IQR |
|---|---|---:|---:|---:|
| 밀도 pt/m2 | raw_dense | 151 | 89.8032 | 13.71-392 |
| 밀도 pt/m2 | raw_acmp | 198 | 77.2229 | 5.991-242.8 |
| 밀도 pt/m2 | raw_lidar | 199 | 18.5787 | 16.05-19.85 |
| 완전성 coverage | raw_dense | 151 | 0.9640 | 0.3979-1 |
| 완전성 coverage | raw_acmp | 198 | 0.8620 | 0.3569-1 |
| 완전성 coverage | raw_lidar | 199 | 0.9979 | 0.9932-1 |
| 노이즈 local RMS m | raw_dense | 144 | 0.1517 | 0.1163-0.183 |
| 노이즈 local RMS m | raw_acmp | 155 | 0.1771 | 0.151-0.2053 |
| 노이즈 local RMS m | raw_lidar | 198 | 0.1498 | 0.1221-0.1686 |
| M3C2 RMS m | raw_dense | 143 | 31.8123 | 24.05-36.41 |
| M3C2 RMS m | raw_acmp | 159 | 1.7212 | 1.373-2.209 |
| M3C2 RMS m | raw_lidar | 0 | none | none |
| 부유점 fraction | raw_dense | 151 | 0.0000 | 0-0 |
| 부유점 fraction | raw_acmp | 198 | 0.0052 | 0.0008652-0.126 |
| 부유점 fraction | raw_lidar | 199 | 0.0010 | 0-0.01831 |
| 라벨 프록시 fraction | raw_dense | 151 | 0.0000 | 0-0 |
| 라벨 프록시 fraction | raw_acmp | 198 | 0.0000 | 0-0.01764 |
| 라벨 프록시 fraction | raw_lidar | 199 | 0.0000 | 0-0 |

그림:

- Arm 대조 분포: `docs/figs/pointcloud_attributes_v1_1/arm_distribution.png`
- ALS 대비 산점: `docs/figs/pointcloud_attributes_v1_1/als_scatter.png`

관찰:
- 밀도: median raw_dense=89.8032, raw_acmp=77.2229, raw_lidar=18.5787.
- 0.5 m 격자 점유율: median raw_dense=0.9640, raw_acmp=0.8620, raw_lidar=0.9979.
- 국소 평면 RMS: median raw_dense=0.1517, raw_acmp=0.1771, raw_lidar=0.1498.
- 부유점 비율: median raw_dense=0.0000, raw_acmp=0.0052, raw_lidar=0.0010.
- 라벨 프록시 비율: median raw_dense=0.0000, raw_acmp=0.0000, raw_lidar=0.0000.

## [A] 높이 상수 출처·민감도

| 상수 시나리오 | 부유점 frac median | n | 라벨 프록시 frac median | n | M3C2 mean median m | n |
|---|---:|---:|---:|---:|---:|---:|
| 48.000 | 0.0006 | 548 | 0.0000 | 548 | -1.8303 | 303 |
| 48.165 | 0.0006 | 548 | 0.0000 | 548 | -1.8303 | 303 |
| 45.760 | 0.0007 | 548 | 0.0000 | 548 | -1.7515 | 303 |

높이상수 관계:

- 같은 자에 올릴 때의 v1.1 채택 상수는 +45.760 m이다. 기준문서 §1.6의 ζ=45.7 m는 논문 본문용 반올림값이고, QA와 계산에는 45.760 m를 썼다.
- +48.000/+48.165는 기존 raw-arm 관행과 v1 참조 비교 상수의 이력값이다. 기준문서 §1.6에 따라 v1.1에서는 확정 상수로 보정하고, 각 행의 `z_datum_history`에 원래 이력과 보정량을 남겼다.

## [B] 104586480 ref_invalid 신규 후보 재료

| arm | n | coverage | ground_label_frac_all | roof_points | z_p05 | z_p50 | z_p95 | pt_density | local_RMS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALS | 175 | 1.0000 | 0.7657 | 41 | 560.820 | 560.870 | 569.813 | 11.848 | 0.137 |
| DIM | 5508 | 1.0000 | 0.5739 | 2347 | 560.800 | 561.030 | 577.650 | 372.898 | 0.152 |

- 그림: `docs/figs/pointcloud_attributes_v1_1/ref_invalid_104586480_topview.png`
- §2.4 본문에 명시된 ID 42364663·42364667과 대조하면 104586480은 그 두 본문 명시 ID가 아니다. P0 기록에는 `W2_1c_reference_mismatch_exclusions.csv`와 `W3_summary.md`에서 reference_mismatch 재료로 이미 남아 있다.
- 재료 성격: ALS와 DIM의 footprint 내부 라벨·높이 분포가 다르고, P0 기록은 시간차/참조 형상/점군 라벨 오류 가능성을 분리하지 않고 reference/temporal mismatch 후보로 남겼다.

## [C] 클립 보강 및 QA

- v1 missing_clip에서 v1.1로 채운 행: raw_dense 149행, raw_lidar 63행.
- v1에서 `missing_lidar_clip`이던 M3C2 중 v1.1에서 재계산된 행: 124행. v1.1에도 남은 `missing_lidar_clip`: 2행.
- v1 대비 변경 사유 상위:
  - datum_constant_v1_14_45p760;unchanged_numeric: 185
  - filled_missing_clip;datum_constant_v1_14_45p760: 150
  - datum_constant_v1_14_45p760: 138
  - datum_constant_v1_14_45p760;m3c2_recomputed_after_lidar_fill: 62
  - filled_missing_clip;datum_constant_v1_14_45p760;m3c2_recomputed_after_lidar_fill: 62
- v1 대비 변경 축 상위:
  - floater_frac: 303
  - label_proxy_frac_all: 261
  - label_proxy_frac_ground: 214
  - clip_source: 212
  - coverage_reason: 212
  - density_reason: 212
  - m3c2_mean_m: 199
  - m3c2_median_abs_m: 199
  - m3c2_rms_m: 199
  - m3c2_reason: 192
  - coverage_frac: 185
  - floater_reason: 185
- 새 raw_dense fallback의 status density delta: n=111, median=3.6695, IQR=-7.199-23.19.
- 큰 density delta 후보(abs(delta)>max(5 pt/m2, 25% status_density)):
  - DEBY_LOD2_104583447: delta=-16.608, attr=20.059, status=36.667
  - DEBY_LOD2_108250120: delta=-17.169, attr=8.693, status=25.862
  - DEBY_LOD2_4906989: delta=-34.466, attr=89.729, status=124.195
  - DEBY_LOD2_4906998: delta=-36.214, attr=43.265, status=79.479
  - DEBY_LOD2_4907017: delta=-15.149, attr=0.184, status=15.333
  - DEBY_LOD2_4907026: delta=-27.458, attr=23.890, status=51.348
  - DEBY_LOD2_4907028: delta=-5.020, attr=0.230, status=5.250
  - DEBY_LOD2_4907165: delta=-71.050, attr=6.703, status=77.753
  - DEBY_LOD2_4907170: delta=-5.408, attr=3.668, status=9.077
  - DEBY_LOD2_4907171: delta=-5.231, attr=3.143, status=8.374
  - DEBY_LOD2_4907176: delta=-31.371, attr=17.094, status=48.465
  - DEBY_LOD2_4907177: delta=-36.820, attr=12.148, status=48.967
  - DEBY_LOD2_4907185: delta=-27.898, attr=22.350, status=50.248
  - DEBY_LOD2_4907186: delta=-7.371, attr=3.223, status=10.594
  - DEBY_LOD2_4907188: delta=-6.156, attr=6.908, status=13.064
  - DEBY_LOD2_4907195: delta=-8.530, attr=6.433, status=14.963
  - DEBY_LOD2_4907198: delta=-9.877, attr=11.718, status=21.595
  - DEBY_LOD2_4907202: delta=-56.568, attr=49.683, status=106.251
  - DEBY_LOD2_4907505: delta=-68.413, attr=33.993, status=102.406
  - DEBY_LOD2_4908163: delta=-6.178, attr=2.364, status=8.542

## [D] 4907019 raw_acmp read-out

- 4907019 raw_acmp orig: rf_roof_planes=2, rf_rmse_lod22=31.020235, val3dity_valid=true; metrics plane_rms=2.935563, roof_density=0.494129.

## [E] 회귀 결과 변수 지문·datum-free 확인

| 항목 | 경로 | sha256 |
|---|---|---|
| status_csv | `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv` | `4412ee47f8665e1a12663629dd66f9c9612f2e9adca54be38c188f2bc521a9b6` |
| w2_config | `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/config.yaml` | `65a8435b8e95b5cbeb86d3a2b82a8fed0b07e62737dc7714062a4151eb24bdd3` |
| w2_versions | `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/versions.txt` | `4a786bdc66cc29732b208b665c5133aa57af848ff38da8e347d77dc001b9c113` |
| w3_repeatability_versions | `phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/versions.txt` | `0071622cde70adc2a4a62e106468fc7d98d59fc6d5587276db7bbe662caf9c82` |
| w3_run2_als_status | `phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/als_default.csv` | `43ad02e993ac250516d7ce75ffb7539276a1f2e7e4e3449cd461e0646f06d613` |
| w3_run2_dim_status | `phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/dim_default.csv` | `625d49898c140c6d1ecf2dc66196b46a962770a240124049ea9b9493fe826ce1` |
| w3_repeatability_building_status | `phases/p0-audit/docs/W3_2b_roofer_repeatability_building_status.csv` | `6a3ca7d8a13407ba0b7ac34cb1d682ccc66aada10adef988a5b4e7d58521c520` |

- attr-v1이 참조한 status CSV는 `w2_1_roofer_default_20260612_152729` 산출물이고, W3 기록의 `w3_2b_roofer_repeatability_20260612_220747/run_2`는 같은 실행이 아니라 같은 명시 기본 파라미터의 별도 실행이다. 어느 쪽을 회귀 결과 변수의 캐노니컬로 쓸지는 판정=김휘영.
- 겹치는 coverage-control 93동 기준 결과 변수 델타:

| input | overlap rows | status diff | val3dity diff | rf_rmse_lod22 numeric nonzero / median / min / max | rf_roof_planes numeric nonzero / median / min / max |
|---|---:|---:|---:|---:|---:|
| ALS | 93 | 5 | 5 | 49 / 0.000 / -0.212 / 0.135 | 16 / 0.000 / -2 / 2 |
| DIM | 93 | 6 | 5 | 63 / 0.000 / -12.051 / 0.341 | 36 / 0.000 / -23 / 10 |

- 반복성 기록 위치: `phases/p0-audit/docs/W3_2b_roofer_repeatability.md`, `phases/p0-audit/docs/W3_2b_roofer_repeatability_building_status.csv`.
- Roofer 버전·파라미터: W2 versions/config와 W3 versions에 기록된 Roofer 1.0.0, val3dity 2.6.0, plane_detect_epsilon=0.3, plane_detect_min_points=15, complexity_factor=0.888.
- 결과 변수 4종은 Roofer 산출 CityJSON attribute와 val3dity report에서 읽힌다. `roofer_ok/roof_surfaces>0`은 CityJSON LOD2.2 geometry 존재, val3dity는 생성 CityJSON 형식 유효성, `rf_roof_planes`와 `rf_rmse_lod22`는 Roofer가 입력 점군으로 만든 모델 내부 속성이다. P0 추출 코드는 `phases/p0-audit/scripts/08_roofer_w2.py`에서 CityJSON attributes를 읽어 status CSV에 쓴다. 외부 LoD2 참조나 이미지 투영 좌표를 다시 쓰는 단계는 없다.

## 판정 필요 지점

- 부유점 여유 3 m를 유지할지.
- 라벨 프록시를 전체 점 대비로 둘지 ground 라벨 내부 비율로 둘지.
- `none` 처리 행을 회귀에서 결측으로 둘지, 결측 자체를 설명변수로 둘지.
- 회귀 사양에서 ref_invalid와 fallback clip_source를 어떻게 층화·제외·고정효과 처리할지.
