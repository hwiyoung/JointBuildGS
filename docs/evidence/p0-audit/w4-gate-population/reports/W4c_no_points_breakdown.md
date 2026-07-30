# W4c — DIM no_points 46동 분해 (안찍힘 / 무텍스처 / 희박 / 불가)

> 작성 2026-06-23. 관찰만, **판정 금지(사람=김휘영)**. EPSG:25832 · Docker(p0-tools) · CPU·읽기전용.
> 입력: 캐노니컬 DIM status CSV(`runs/w2_1_roofer_default_20260612_152729/building_reconstruction_status.csv`,
> reason=`pointcloud_unusable_no_points` ∧ input=DIM = 46동) · 원본 UAV 영상 937 · COLMAP 포즈(OPF georef,
> EPSG:25832) · LoD2 footprint GPKG · ALS 4타일. **T9(`09_failure_surface_cause.py`) 기하·텍스처 함수 그대로
> import 재사용**(project/incidence/near-nadir 20°/텍스처 gradient/ALS surface). 드라이버 `scripts/v6_no_points_breakdown.py`.

## 임계 (DIM-success 대조 40동에서 유도, 공개)
- `near_nadir_view_count_min = 3.0` (대조 near-nadir p10) · near-nadir = 입사각 ≤20°
- `near_texture_low = 0.02333` (대조 near-nadir 텍스처 gradient p10) · `oblique_texture_low = 0.02525` (대조 oblique p10)

## 분류 규칙 (공개)
- **a 안찍힘**: all_view_count ≤ 2 (등록영상 ~0)
- near-nadir ≥ 3:
  - near-텍스처 ≥ 0.0233 → **e 기타**(near-nadir+텍스처 있는데 0점; overlap/baseline)
  - near-텍스처 < 0.0233 → near-nadir ≥ 6이면 **d 불가**, 아니면 **b 무텍스처**
- near-nadir < 3 (대부분 0)이나 촬영됨:
  - oblique-텍스처 < 0.0253 → **b 무텍스처**(오블리크로도 무텍스처 → prior 필요)
  - 아니면 → **c near-nadir 결손**(오블리크 텍스처 정상 → 나디르 재촬영으로 해결)

## 결과 (46동)
| 갈래 | n | 해석 |
|---|---:|---|
| **a 안찍힘** | **0** | 비행 밖 0동 (모두 등록영상 다수) |
| **c near-nadir 결손** | **36** | near-nadir=0·오블리크 ~185뷰·오블리크텍스처 정상(med 0.029)·ALS 36/36 관측 → **나디르 재촬영으로 해결 가능** |
| **b 무텍스처** | **5** | near-nadir 또는 오블리크 텍스처가 임계 미만 → **prior/방법 필요** |
| **d 불가** | **3** | near-nadir 8~26 충분한데도 무텍스처(텍스처 0.021~0.022) → **센서 본질 한계** |
| **e 기타** | **2** | near-nadir+텍스처 있는데 0점 (overlap/baseline·소형지붕 의심) |

### b/d/e 동별 (c 36동은 동질: near_nadir=0·오블리크텍스처 정상·ALS 관측 — 전체표는 CSV)
| 갈래 | building | all_v | near_nadir | nadirTex | oblTex | ALS pts |
|---|---|---:|---:|---:|---:|---:|
| d 불가 | DEBY_LOD2_42364607 | 285 | 26 | 0.0213 | 0.0322 | 1611 |
| d 불가 | DEBY_LOD2_4908167 | 291 | 8 | 0.0215 | 0.0254 | 605 |
| d 불가 | DEBY_LOD2_4908169 | 280 | 13 | 0.0223 | 0.0267 | 310 |
| b 무텍스처 | DEBY_LOD2_4908160 | 213 | 3 | 0.0207 | 0.0247 | 121 |
| b 무텍스처 | DEBY_LOD2_8568391 | 294 | 4 | 0.0201 | 0.0239 | 947 |
| b 무텍스처 | DEBY_LOD2_8568392 | 274 | 4 | 0.0168 | 0.0204 | 109 |
| b 무텍스처 | DEBY_LOD2_108247350 | 264 | 0 | – | 0.0203 | 168 |
| b 무텍스처 | DEBY_LOD2_108247351 | 266 | 0 | – | 0.0252 | 1206 |
| e 기타 | DEBY_LOD2_4907199 | 287 | 3 | 0.0292 | 0.0224 | 2047 |
| e 기타 | DEBY_LOD2_4908054 | 180 | 21 | 0.0254 | 0.0259 | 370 |

## 관찰 (판정 금지)
- **대다수(36/46, 78%)는 near-nadir 결손**: all_view ~185(오블리크)인데 near-nadir(≤20°) **정확히 0**. 오블리크 텍스처는
  정상(med 0.029 > 0.025), ALS는 36/36 관측 → 건물은 있고 위에서 보이나 **UAV 나디르 패스가 주변부를 안 덮음**.
  → "뷰 적음(희박)"이 아니라 **촬영 기하(near-nadir 커버리지) 결손**; **나디르 재촬영으로 해결 가능** 범주.
- **본질 한계는 소수**: d 불가 3(near-nadir 8~26 충분한데도 무텍스처) + b 무텍스처 5 = **8/46**만이 영상-스테레오로 어려움.
- **a 안찍힘 0**: 모든 46동이 등록영상 다수 → "비행 밖" 사례 없음.
- e 2동: near-nadir 텍스처가 임계 위인데 DIM 0점 → overlap/baseline·소형지붕 등 별도 원인 의심(추가 확인 여지).

## 한 줄 (판정 금지)
**no_points 46동 = 센서/방법 본질 한계(d 3 + b 5 = 8) vs 나디르 재촬영으로 해결(c 36) vs 미촬영(a 0).**
즉 영상-유래 0점 실패의 **대부분(36/46)은 near-nadir 커버리지 결손(촬영 기하)으로 재촬영 가능**, 본질적 무텍스처/불가는 8/46.
ALS는 46동 전부 관측 → 결손은 UAV 나디르 비행계획 문제이지 대상 부재가 아님.

## 산출
- `docs/W4c_no_points_breakdown.csv`(46동 전체) · `_meta.json`(counts·thresholds) · 드라이버 `scripts/v6_no_points_breakdown.py`.
