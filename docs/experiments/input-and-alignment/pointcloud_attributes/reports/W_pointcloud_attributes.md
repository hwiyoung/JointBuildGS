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
- v1의 +48.0은 `scripts/input_and_alignment/p2_gsjso/tum_mob_raw_to_npz.py`와 `docs/W_pointcloud_attributes.md`의 ACMP/LiDAR raw-arm 관행값이다. v1.1에서는 orthometric ACMP/ALS에 +45.760 m를 썼다.
- v1의 +48.165는 `scripts/evidence_and_attributes/p2_gsjso/pointcloud_attributes_v1.py`의 `GEOID_MED_M`으로, 참조 LoD2 지붕 Z를 raw-arm 높이와 비교할 때만 더했던 값이다.
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

---

# W pointcloud attributes v1.2

> 재구성/재학습 없음. 이미지-투영 불사용. 수치와 관찰만 기록한다. CRS는 EPSG:25832.

## v1.2 입력·수리 범위

- 기준문서 확인: 루트 기준문서 v1.14 (2026-07-05).
- 본 수리는 `raw_dense`의 `fallback_dim_footprint_clip` 149행만 대상으로 했다. 밀도·완전성·국소 평면 RMS는 v1.1 값을 보존했다.
- W1 기록: `dim_v1_classified_z.laz`는 GCG2016 보정본이고, W2 기록: `dim_v1_classified_z_minus0p174.laz`는 `Z := Z - 0.174 m`로 만든 입력이다.
- v1.2 dense fallback 높이 이동: +45.934 m (= 45.760 + 0.174). 근거 파일은 `W1_diagnosis.md`, `07_vertical_align.py`, `08_roofer_w2.py`, W2 config이며, W2 config의 기록 커밋은 `d61ff0f7386ba4df3e61a75443d9b84346c44387`이다.
- `z_datum_history`에는 W1 GCG2016 보정, W2 `-0.174 m`, v1.2 `+45.934 m` 이동을 남겼다.

## v1.2 클립 출처

| arm | source | n_rows |
|---|---|---:|
| raw_dense | existing_mob_eval_clip | 50 |
| raw_dense | fallback_dim_footprint_clip | 149 |
| raw_acmp | existing_mob_eval_clip | 68 |
| raw_acmp | fallback_fused_acmp_footprint_clip | 131 |
| raw_lidar | existing_mob_eval_clip | 136 |
| raw_lidar | fallback_als_footprint_clip | 63 |

## v1.2 축별·입력 종류별 분포

| 축 | 입력 종류 | n | median | IQR |
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
| M3C2 RMS m | raw_dense | 143 | 0.3410 | 0.1723-0.5796 |
| M3C2 RMS m | raw_acmp | 159 | 1.7212 | 1.373-2.209 |
| M3C2 RMS m | raw_lidar | 0 | none | none |
| 부유점 fraction | raw_dense | 151 | 0.0030 | 0-0.02985 |
| 부유점 fraction | raw_acmp | 198 | 0.0052 | 0.0008655-0.126 |
| 부유점 fraction | raw_lidar | 199 | 0.0010 | 0-0.01831 |
| 라벨 프록시 fraction | raw_dense | 151 | 0.0000 | 0-0.1483 |
| 라벨 프록시 fraction | raw_acmp | 198 | 0.0000 | 0-0.01764 |
| 라벨 프록시 fraction | raw_lidar | 199 | 0.0000 | 0-0 |

그림:

- 입력 종류 대조 분포: `docs/figs/pointcloud_attributes_v1_2/arm_distribution.png`
- ALS 대비 산점: `docs/figs/pointcloud_attributes_v1_2/als_scatter.png`

## v1.2 자가 게이트

| 항목 | 수리 전 | 수리 후 | 기존 dense clip | 통과 |
|---|---:|---:|---:|---|
| dense fallback M3C2 RMS median m | 33.1788 | 0.3271 | existing n/a | True |
| dense fallback M3C2 mean median_abs m | 28.5147 | 0.1099 | existing n/a | False |
| dense fallback M3C2 mean median m | -28.5147 | 0.0971 | existing n/a | 기록 |
| 부유점 0 아닌 행 수 | 0 | 77 | 16/50 | True |
| 라벨 프록시 0 아닌 행 수 | 0 | 36 | 20/50 | True |
| 기존 유효 행 metric 변경 수 | n/a | 0 | n/a | True |
| dense fallback 보존 축 변경 수 | n/a | 0 | n/a | True |

- 게이트 요약: A=True, B=True, C=True.
- A는 v1/v1.1 분포표와 같은 `M3C2 RMS median` 기준이다. `M3C2 mean median_abs`는 보조 기록으로 함께 남겼다.

## v1.2 변경 로그

- dense fallback 149행 중 `n_points_footprint>0` 행의 부유점·라벨·M3C2 축을 재계산했다. no_points 행의 metric 값은 그대로 두고 높이 이력 열만 갱신했다.
- 기존 유효 행의 metric 변경 수는 위 게이트 표에 기록했다.

## 104586480 ref_invalid 후보 재료

| 입력 종류 | n | coverage | ground_label_frac_all | roof_points | z_p05 | z_p50 | z_p95 | pt_density | local_RMS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALS | 175 | 1.0000 | 0.7657 | 41 | 560.820 | 560.870 | 569.813 | 11.848 | 0.137 |
| DIM | 5508 | 1.0000 | 0.5739 | 2347 | 560.800 | 561.030 | 577.650 | 372.898 | 0.152 |

- 그림: `docs/figs/pointcloud_attributes_v1_2/ref_invalid_104586480_topview.png`
- §2.4 본문 명시 ID 42364663·42364667과 대조하면 104586480은 그 두 본문 명시 ID가 아니다. v1.1과 같은 P0 기록에는 후보 재료로 남아 있다.
- 관찰 재료: ALS 내부는 지면 라벨 우세·지면 높이 분포이고, DIM은 더 높은 구조물 성분을 포함한다. 시간차·참조 형상·점군 라벨 오류 중 어느 쪽인지는 여기서 판정하지 않는다.

## dense fallback status-density QA

- 새 raw_dense fallback의 status density delta: n=111, median=3.6695, IQR=-7.1991-23.1928.
- 큰 density delta 기준: abs(delta)>max(5 pt/m2, 25% status_density). v1.1 보고서는 28동 중 앞 20동만 출력했으므로, v1.2에서는 전체 28동을 같은 기준으로 적는다.

| building_id | delta | attr_density | status_density | note |
|---|---:|---:|---:|---|
| DEBY_LOD2_104583447 | -16.608 | 20.059 | 36.667 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_108250120 | -17.169 | 8.693 | 25.862 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4906989 | -34.466 | 89.729 | 124.195 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4906998 | -36.214 | 43.265 | 79.479 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907017 | -15.149 | 0.184 | 15.333 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907026 | -27.458 | 23.890 | 51.348 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907028 | -5.020 | 0.230 | 5.250 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907165 | -71.050 | 6.703 | 77.753 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907170 | -5.408 | 3.668 | 9.077 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907171 | -5.231 | 3.143 | 8.374 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907176 | -31.371 | 17.094 | 48.465 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907177 | -36.820 | 12.148 | 48.967 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907185 | -27.898 | 22.350 | 50.248 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907186 | -7.371 | 3.223 | 10.594 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907188 | -6.156 | 6.908 | 13.064 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907195 | -8.530 | 6.433 | 14.963 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907198 | -9.877 | 11.718 | 21.595 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907202 | -56.568 | 49.683 | 106.251 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4907505 | -68.413 | 33.993 | 102.406 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4908163 | -6.178 | 2.364 | 8.542 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4908168 | -42.245 | 28.545 | 70.791 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4908178 | -21.592 | 17.282 | 38.874 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4908351 | -13.203 | 0.797 | 14.000 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_4959320 | -94.374 | 6.141 | 100.515 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_60097 | -33.283 | 8.521 | 41.803 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_60098 | -6.628 | 3.440 | 10.068 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_8568403 | -15.305 | 15.273 | 30.578 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |
| DEBY_LOD2_8573848 | -27.631 | 62.416 | 90.047 | fallback footprint all-point density below status rf_pt_density; metric definition/source selection differs |

## 결과 정본 런 델타 재료

| 입력 종류 | w2_1 rows | run_2 rows | overlap rows | has_lod22 flips | val3dity flips | rmse nonzero/median/IQR/min/max | roof_planes nonzero/median/IQR/min/max |
|---|---:|---:|---:|---:|---:|---|---|
| ALS | 199 | 93 | 93 | 0 | 5 | 54/0.0000/-0.0000-0.0000/-0.2116/0.1354 | 16/0.0000/0.0000-0.0000/-2.0000/2.0000 |
| DIM | 199 | 93 | 93 | 1 | 5 | 64/0.0000/-0.0009-0.0002/-12.0512/0.3405 | 36/0.0000/0.0000-0.0000/-23.0000/10.0000 |

- 겹치는 동별 델타 CSV: `docs/experiments/input-and-alignment/pointcloud_attributes/tables/W_canonical_run_delta.csv`.
- 조립 성공 flip IDs:
  - DIM DEBY_LOD2_42364663: w2=True, run_2=False
- 유효성 flip IDs:
  - ALS DEBY_LOD2_108580336: w2=False, run_2=True
  - ALS DEBY_LOD2_4906975: w2=True, run_2=False
  - ALS DEBY_LOD2_4907178: w2=False, run_2=True
  - ALS DEBY_LOD2_4907506: w2=False, run_2=True
  - ALS DEBY_LOD2_4907514: w2=False, run_2=True
  - DIM DEBY_LOD2_108580335: w2=True, run_2=False
  - DIM DEBY_LOD2_4906968: w2=False, run_2=True
  - DIM DEBY_LOD2_4906969: w2=False, run_2=True
  - DIM DEBY_LOD2_4907519: w2=False, run_2=True
  - DIM DEBY_LOD2_4907521: w2=True, run_2=False
- 관찰: w2_1은 입력 종류별 199동 전수이고, run_2는 입력 종류별 93동 coverage-control 부분집합이다. 위 표는 겹치는 93동 기준의 수치 차이다.

## 104586480 날짜 재료

| building_id | LoD2 creationDate | LoD2 source | ALS date material | ALS source | UAV capture date | UAV source |
|---|---|---|---|---|---|---|
| DEBY_LOD2_104586480 | 2025-04-04 | `phases/p0-audit/data/raw/lod2/690_5334.gml` | LAZ header creation date 2022-06-16; adjusted GPS time 2022-02-27 | `phases/p0-audit/docs/data_inventory.md` | 2024-12-17 | `docs/experiments/input-and-alignment/pointcloud_attributes/reports/flight_meta_summary.md` |

## 입력 지문

| 항목 | 경로 | sha256 |
|---|---|---|
| v1_1_csv | `docs/pointcloud_attributes_v1_1.csv` | `22b158810d5b667c2ef71a5e70b682a7de23faa7a5e29b3422780c421bd71b04` |
| dim_fallback_source_w2_minus0p174 | `phases/p0-audit/data/work/w2/dim_v1_classified_z_minus0p174.laz` | `f91929924af251d802ec71d9d246caa3194faa72cf82d739d474cd7dc2b1931d` |
| als_fallback_source | `results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz` | `ac5cd0dc9c368a15e1f8fd5a18ad8d96ddbbd8cbaf8e1b608fd675430d6e9225` |
| w1_diagnosis | `phases/p0-audit/docs/W1_diagnosis.md` | `d2775c436a74362f74ee2819b833ab0bb055e4533e08f15aa1c814ed53866814` |
| w1_vertical_align_script | `phases/p0-audit/scripts/07_vertical_align.py` | `bc705c1fee3df8aacc8bd9e2a1be1336d13faa541e2d2fb12e6a4d397560ef94` |
| w2_roofer_script | `phases/p0-audit/scripts/08_roofer_w2.py` | `ae655090915c56bfeee2be830a28e27520c2430e97d19e515a0aa046e4c79e97` |
| w2_config | `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/config.yaml` | `65a8435b8e95b5cbeb86d3a2b82a8fed0b07e62737dc7714062a4151eb24bdd3` |
| w2_status | `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv` | `4412ee47f8665e1a12663629dd66f9c9612f2e9adca54be38c188f2bc521a9b6` |
| w3_run2_als_status | `phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/als_default.csv` | `43ad02e993ac250516d7ce75ffb7539276a1f2e7e4e3449cd461e0646f06d613` |
| w3_run2_dim_status | `phases/p0-audit/runs/w3_2b_roofer_repeatability_20260612_220747/status/run_2/dim_default.csv` | `625d49898c140c6d1ecf2dc66196b46a962770a240124049ea9b9493fe826ce1` |

## 판정 필요 지점

- 부유점 여유 3 m 유지 여부.
- 라벨 프록시 정의: 전체 점 대비 `label_proxy_frac_all`과 ground 내부 `label_proxy_frac_ground` 중 회귀 주지표 선택.
- `none` 행 처리: no_points 재코딩은 회귀 사양에서 처리.
- 결과 정본 런 선택과 회귀 사양은 B단계 판정 뒤 실행.
