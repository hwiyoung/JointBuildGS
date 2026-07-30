# aux_v4b_change_report -- lowtex-v5 and evidence cards v3

> 재구성/재학습 없음. 판정 금지. 수치·관찰만 기록한다.

## 0. 입력과 규약

- image-projection zeta = 45.700 m. 3D/씨드 경로 `-556`은 건드리지 않았다.
- 지오 산출물 CRS: EPSG:25832. OPF/COLMAP frame: EPSG:32632.
- lowtex-v5 view rule: 지붕 100% in-frame AND frame radius <0.85 AND 기울기 최소. 해당 view가 없으면 `lowtex_valid=none`.
- card render rule: LiDAR points가 판정 채널이고 LoD2 ring은 context이며 caption 공차는 +/-1 m.

## 1. lowtex-v5 산출

- `valid`: 199동.
- `none`: 0동.
- v5 분포(valid): {'n': 199, 'min': 0.104, 'median': 0.533, 'max': 0.846}.
- CSV: `docs/experiments/input-and-alignment/lowtex_v5/tables/lowtex_v5.csv`, `docs/experiments/input-and-alignment/lowtex_v5/tables/lowtex_v5_anchor_check.csv`.

## 2. 텍스처 앵커 11동

| building_id | anchor | clean_negative_used | lowtex_valid | roof_lowtex_v5 | view | zenith_deg | frame_r |
|---|---|---:|---|---:|---|---:|---:|
| DEBY_LOD2_4907182 | positive_lowtex | 0 | valid | 0.738 | `DJI_20241217084711_0139_D.JPG` | 60.991 | 0.761 |
| DEBY_LOD2_42364609 | positive_lowtex | 0 | valid | 0.546 | `DJI_20241217084535_0091_D.JPG` | 60.337 | 0.623 |
| DEBY_LOD2_4907510 | positive_lowtex | 0 | valid | 0.554 | `DJI_20241217084643_0125_D.JPG` | 18.409 | 0.668 |
| DEBY_LOD2_4908050 | positive_lowtex | 0 | valid | 0.244 | `DJI_20241217084521_0084_D.JPG` | 60.146 | 0.827 |
| DEBY_LOD2_4908166 | positive_lowtex | 0 | valid | 0.599 | `DJI_20241217084535_0091_D.JPG` | 60.126 | 0.665 |
| DEBY_LOD2_4908176 | positive_lowtex | 0 | valid | 0.293 | `DJI_20241217084731_0149_D.JPG` | 60.652 | 0.52 |
| DEBY_LOD2_4906972 | negative_textured | 1 | valid | 0.125 | `DJI_20241217084407_0047_D.JPG` | 7.22 | 0.594 |
| DEBY_LOD2_4908023 | negative_textured | 0 | valid | 0.288 | `DJI_20241217084841_0184_D.JPG` | 15.648 | 0.47 |
| DEBY_LOD2_4907028 | negative_textured | 1 | valid | 0.708 | `DJI_20241217103501_0040_D.JPG` | 84.19 | 0.722 |
| DEBY_LOD2_4908354 | negative_textured | 1 | valid | 0.29 | `DJI_20241217084643_0125_D.JPG` | 11.517 | 0.381 |
| DEBY_LOD2_4907520 | negative_textured | 1 | valid | 0.104 | `DJI_20241217084345_0036_D.JPG` | 2.24 | 0.372 |

- 양성 6동 v5 min/mean: 0.244 / 0.496.
- 음성 5동 v5 max/mean: 0.708 / 0.303.
- clean 음성 4동(4908023 제외) v5 max/mean: 0.708 / 0.307.
- all-anchor gap(pos_min - neg_max): -0.464.
- clean gap(pos_min - clean_neg_max): -0.464.
- 관찰: lowtex-v5 strict view에서는 앵커 분리가 유지되지 않았다. clean gap 음수는 4907028(v5=0.708, zenith=84.19 deg)이 음성 최대값이 된 영향이다.
- 4908023은 이전 문서에서 텍스처 앵커 부적합 관찰이 있어 clean 음성 계산에서 별도 제외했다.

## 3. v4<->v5 이동 상위 10동

| rank | building_id | roof_lowtex_v4 | roof_lowtex_v5 | delta_v5_minus_v4 | v5_view | valid |
|---:|---|---:|---:|---:|---|---|
| 1 | DEBY_LOD2_4907028 | 0.038 | 0.708 | +0.670 | `DJI_20241217103501_0040_D.JPG` | valid |
| 2 | DEBY_LOD2_4908051 | 0.772 | 0.197 | -0.575 | `DJI_20241217084757_0162_D.JPG` | valid |
| 3 | DEBY_LOD2_4907021 | 0.762 | 0.239 | -0.523 | `DJI_20241217084757_0162_D.JPG` | valid |
| 4 | DEBY_LOD2_42364663 | 0.921 | 0.446 | -0.475 | `DJI_20241217084727_0147_D.JPG` | valid |
| 5 | DEBY_LOD2_4908026 | 0.733 | 0.278 | -0.455 | `DJI_20241217084729_0148_D.JPG` | valid |
| 6 | DEBY_LOD2_4907017 | 0.171 | 0.625 | +0.454 | `DJI_20241217101335_0020_D.JPG` | valid |
| 7 | DEBY_LOD2_4908025 | 0.773 | 0.353 | -0.420 | `DJI_20241217084729_0148_D.JPG` | valid |
| 8 | DEBY_LOD2_4908050 | 0.657 | 0.244 | -0.413 | `DJI_20241217084521_0084_D.JPG` | valid |
| 9 | DEBY_LOD2_4907016 | 0.993 | 0.585 | -0.408 | `DJI_20241217095143_0078_D.JPG` | valid |
| 10 | DEBY_LOD2_4908027 | 0.671 | 0.273 | -0.398 | `DJI_20241217084729_0148_D.JPG` | valid |

## 4. evidence_cards_v3

- manual_review cards: 44.
- time_diff cards: 3.
- skipped: 0.
- manifest: `docs/evidence/evidence_cards_v3/manifest.csv`.
- README: `docs/evidence/evidence_cards_v3/README.md`.

## 5. datum_tie_overlay corner zoom refresh

| building_id | status | view | zenith_deg | figure |
|---|---|---|---:|---|
| DEBY_LOD2_4906966 | refreshed | `DJI_20241217095507_0036_D.JPG` | 60.806 | `docs/figs/datum_tie_overlay/4906966_strong_corner_zoom.png` |
| DEBY_LOD2_4906969 | refreshed | `DJI_20241217103103_0008_D.JPG` | 59.985 | `docs/figs/datum_tie_overlay/4906969_strong_corner_zoom.png` |

## 6. 관찰

- lowtex-v5는 199동 중 199동에서 strict view rule을 만족했다.
- 텍스처 앵커는 11동 모두 재측정됐지만 clean gap이 음수라 분리 유지 관찰은 나오지 않았다.
- A3a의 취득 한계/수동판정 분류 규칙은 이 커밋에서 다시 바꾸지 않았다.
- 카드와 corner zoom은 projection/render 산출이며 사진 매칭·재측정 산출이 아니다.

## 7. 판정 필요 지점

1. lowtex-v5 199/199 valid 산출을 수동판정 세션 입력으로 둘지 여부.
2. 텍스처 앵커 clean gap 음수와 4907028 강기울기 v5 값을 lowtex 임계 논의에 어떻게 반영할지 여부.
3. evidence_cards_v3 수동판정 대상 목록과 시간차 3동 목록을 확정할지 여부.
4. A3a 15·6·27 변동(2·2·44)을 이후 subclass 재유도 입력으로 둘지 여부.
