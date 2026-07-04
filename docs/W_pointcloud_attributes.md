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
