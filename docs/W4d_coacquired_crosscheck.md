# W4d — no_points 46동 귀속: 동시취득 데이터 대조. 관찰만, 판정=김휘영.

> 작성 2026-06-24. branch feature/p2-seed-protect(데이터만 읽음). EPSG:25832 · Docker(p0-tools) · CPU·읽기전용.
> no_points 36(W4c near-nadir 결손)+b5+d3+e2를 영상과 **동일 L2 플랫폼 동시취득** 데이터로 귀속:
> (i) 내 COLMAP+OpenMVS 특유 / (ii) MVS 일반 한계 / (iii) 취득(커버리지) 한계.
> 번들 = TUM2TWIN Zenodo 14548134 (Pix4D dense 4.0GB·ULS nadir 1.2GB·ULS manual 1.5GB, **EPSG:32632**→25832 재투영).
> 스크립트 `b2_bundle_prep.sh`(reproject+decimate)·`b2_roof_count.py`(footprint 점수). 산출 `results/.../b2/material_46x6.csv`.

## Phase 0
- 번들 CRS = **EPSG:32632(WGS84/UTM32N)** 확정 → 25832(ETRS89) 재투영(~0.7m). 46/46 footprint이 번들 bbox 안(Pix4D 46·ULS-nadir 46·ULS-manual 2 centroid).
- **재투영 검증(버그 아님)**: ULS-nadir(재투영)는 make-or-break 코어를 **조밀 커버**(4906972 in-fp 68,463점·nearest 0.0m; 4906969 17,412; 42364663 10,404) — 좌표 정확. 그런데 **no_points footprint엔 0점**(4907012 nearest 65m·in-fp 0; 104583794 20m·0). 즉 실제 데이터 결손(버그 ✗).

## Phase 1 — 6원천 × 46동 footprint 점유 (점≥20=커버, decimation 보정)
**원천별 커버 동수 (of 46):**
| 원천 | 측 | 커버 /46 |
|---|---|---:|
| DIM (내 COLMAP+OpenMVS) | 영상 | 4 |
| OPF/COLMAP-sparse | 영상 | 0 |
| Pix4D-dense (독립 MVS) | 영상 | 4 |
| **L2-ULS-nadir (동시취득 LiDAR)** | LiDAR | **2** |
| L2-ULS-manual (동시취득, oblique) | LiDAR | 0 |
| **Bavaria-ALS (별도 완전측량)** | LiDAR(ref) | **46** |

→ **동시취득 L2 전 원천(카메라-MVS·Pix4D·ULS-nadir)이 42~44/46을 놓침. 오직 Bavaria-ALS(별도 항공측량)만 46/46 커버.**

## 귀속 (regel: Pix4D/sparse≥20→i / 아니고 ULS≥20→ii / 둘 다 무→iii)
| 갈래 | n /46 | (c36 중) | 의미 |
|---|---:|---:|---|
| **iii 취득/커버리지 한계** | **41** | 34/36 | 동시취득 카메라·Pix4D·ULS-nadir 전부 0, Bavaria-ALS만 → **L2 나디르 패스가 이 건물을 카메라·LiDAR 둘 다 놓침**(완전측량/재촬영 필요) |
| **i 내 COLMAP+OpenMVS 특유** | **4** | 2/36 | Pix4D dense는 복원, 내 DIM=0 (4906999·4908049·4908169·8568391) |
| **ii MVS 일반 한계** | **1** | 0 | ULS-nadir만 점(4908167), 영상 MVS(내것·Pix4D) 모두 0 |

## 관찰 (판정 금지)
1. **동시취득 LiDAR도 no_points를 못 잡는다(42~44/46)** — ULS-nadir이 코어는 6.8만점 조밀 커버하나 이 건물들엔 0점. → **MVS 중간표현 약점이 아니라 L2 플랫폼 나디르 커버리지 결손**(카메라 near-nadir + LiDAR nadir 동반 결손). W4c "near-nadir 결손, 재촬영 가능"을 **동시취득 LiDAR로 확증**(같은 패스에서 LiDAR도 구멍).
2. **유일하게 Bavaria-ALS(별도 완전 항공측량)만 46/46 커버** — 즉 더 완전한 취득(재촬영/타 플랫폼)으로 회복 가능, 현 L2 동시취득 데이터로는 영상·LiDAR 공히 불가.
3. **내 파이프라인 특유는 소수(4/46)** — Pix4D(상용 독립 MVS)가 복원한 곳에서 내 COLMAP+OpenMVS만 0 → 그 4동은 내 MVS 파이프라인 개선으로 회복 가능.
4. **취득 한계의 본질(가설, 판정=사람)**: 코어는 동시취득 LiDAR가 조밀한데 특정 건물만 구멍 → 나디르 비행라인 간 간격/오클루전(저층·안마당) 의심. 영상 oblique는 봤으나(W4c 189뷰) 나디르 스테레오·LiDAR는 결손.

## 한 줄 (판정 금지)
**no_points 46 중 41(34/36 near-nadir-gap)은 동시취득 카메라·Pix4D·ULS-nadir 전부 0이고 Bavaria-ALS만 커버 = 취득/커버리지 한계(MVS 약점·내 파이프라인 아님), 내 COLMAP+OpenMVS 특유는 4, MVS 일반은 1.** → 영상-유래 0점의 대다수는 L2 나디르 커버리지 결손으로, 동시취득 LiDAR로도 미회복(완전측량/재촬영 필요).

## 산출
- `results/tum_transfer/mob/b2/material_46x6.csv` (46동 × 6원천 점수·밀도·귀속) · b2_bundle_prep.sh · b2_roof_count.py · b2_coverage_check.py.
