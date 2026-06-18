# 단계 1c — TSDF 점추출 + Roofer 바닥 + 1동 end-to-end (build A 진입 결정)

> **일자:** 2026-06-18 · **branch:** `feature/p2-gsjso` · **판정은 사람 — 측정·관찰까지(판정 금지).**
> **목적:** 1b에서 GS *센터* 점군이 ALS 대비 13~200× 희박·floater 많음이 확인됨. 표준 방법(2DGS depth→융합)으로
> 바꿔 ① Roofer가 요구하는 *바닥* 측정, ② TSDF 점군이 그 바닥을 넘는지, ③ 넘으면 텍스처 1동 end-to-end(→CityJSON).
> **실패 귀속을 깨끗이**: 점추출 *방법*(센터→TSDF) 탓 vs *GS depth 품질* 탓 분리. **엔진 로직 무변경(별도 스크립트), 재학습 없음**(7k ckpt 소비).

## 방법 (file:line)

- **점추출 = 2DGS 정식 surface**: `rasterization_2dgs`로 각 뷰 **median depth**(`render_median`) 렌더 + **accumulated
  opacity>0.5** 마스크 → 백프로젝션 → 0.05 m voxel 융합 → Open3D statistical outlier 제거. (`renderer.py:67,92` median/alpha;
  추출 `scripts/stage2/tum_tsdf_extract.py`.) 500 m 장면이라 균일 TSDF volume 대신 "fused depth 점"(설계 허용 대안), 텍스처
  3동 box(+15 m)로 클립. 937뷰, downscale 2(depth는 학습해상도 무관).
- **분류 = P0 T4 그대로**: PDAL `filters.smrf`(ground=2) + `filters.overlay` footprint(building=6) — `04_classify.py:193-224`.
- **Roofer = P0 그대로**: `docker compose -f phases/p0-audit/env/docker-compose.p0.yml run roofer --id-attribute building_id
  --box … <laz> footprints_scene_aoi.gpkg <out>` (`08_roofer_w2.py:86-105`); val3dity는 `combine_cityjsonseq`+`tools val3dity`.
- 좌표(1b 확정): **EPSG:25832 = GS_local + [690953,5336071,604]**. TSDF/ALS 모두 25832.

## ① Roofer 바닥 (decimated/noised ALS → Roofer → val3dity)

3 reps box. 밀도 sweep(noise 0) + 노이즈 sweep(density 8). 셀 = `roofsurfaces / val3dity`.

| config | 목표밀도 | 노이즈σ(m) | 실측밀도 | 4906972 | 4906969 | 4908023 |
|---|---|---|---|---|---|---|
| d16 | 16 | 0 | 14.96 | 3/valid | 7/valid | 1/valid |
| d8 | 8 | 0 | 8.00 | 3/valid | 6/valid | 1/valid |
| d4 | 4 | 0 | 4.00 | 3/valid | 3/valid | 1/valid |
| d2 | 2 | 0 | 2.00 | 3/valid | 2/valid | 1/valid |
| **d1** | 1 | 0 | 1.00 | 2/valid | 1/valid | 1/valid |
| n0.1 | 8 | 0.1 | 8.00 | 3/valid | 5/valid | 1/valid |
| n0.2 | 8 | 0.2 | 8.00 | 3/valid | 4/valid | 1/valid |
| n0.5 | 8 | 0.5 | 8.00 | 5/valid | 4/valid | 1/valid |
| **n1.0** | 8 | 1.0 | 8.00 | 4/valid | 1/valid | 1/valid |

**바닥(관찰):** Roofer는 **밀도 1 pt/m²까지, z-노이즈 σ=1.0 m까지 전부 유효 모델 생성**(지붕면만 단순화). 즉 바닥이 매우
관대 — 밀도 하한 ≤1 pt/m², 노이즈 상한 ≥1.0 m(시험 범위 내 미붕괴).

## ② TSDF 품질 — 센터(1b) vs TSDF vs ALS vs 바닥

footprint 클립 후 지붕 점밀도·평면 RMS·floater%. 그림(top/side, 센터|TSDF|ALS):
[4906972](figs/tum_transfer/tsdf_4906972.png) · [4906969](figs/tum_transfer/tsdf_4906969.png) · [4908023](figs/tum_transfer/tsdf_4908023.png).

| building | source | n_pts | roof_dens(pts/m²) | plane_RMS(m) | floater% |
|---|---|---|---|---|---|
| 4906972 (371 m²) | GS-center | 644 | 1.48 | 3.20 | 33.5 |
| | **TSDF** | 1,280,787 | **2923** | **3.46** | **24.6** |
| | ALS | 8,012 | 20.16 | 2.65 | 0.0 |
| 4906969 (173 m²) | GS-center | 55 | 0.32 | 0.72 | 0.0 |
| | **TSDF** | 186,459 | **962** | **2.01** | **11.2** |
| | ALS | 3,407 | 18.20 | 1.71 | 8.2 |
| 4908023 (22 m²) | GS-center | 2 | 0.09 | n/a | 0.0 |
| | **TSDF** | 56,784 | **1503** | **0.77** | **1.3** |
| | ALS | 448 | 18.48 | 0.24 | 0.0 |

**관찰:**
- **TSDF는 센터의 희박 문제를 해소**: 밀도 0.09–1.48 → **962–2923 pts/m²**(ALS 20보다도 훨씬 조밀, 바닥 1 pt/m²의 ~1000×).
  센터 2점뿐이던 4908023도 TSDF 56,784점. → *밀도 병목은 "센터"라는 방법 탓이었고 표준 depth-융합으로 해소*.
- **그러나 TSDF 표면은 노이즈/두꺼움**: 평면 RMS 0.77–3.46 m(4906972는 ALS 2.65보다 거칢), floater 1.3–24.6%. 노이즈가
  건물 크기/복잡도에 따라 커짐(소형 4908023 0.77 m 최청결, 대형 4906972 3.46 m 최노이즈). 원인 = 7k vanilla depth의 거칢
  (기하 prior 없음·저반복). 바닥의 노이즈 상한(시험 ≤1.0 m valid)과 비교: 4908023(0.77<1.0)은 범위 내, 4906969(2.01)·
  4906972(3.46)는 시험 범위 초과.

## ③ 1동 end-to-end — 4906972 (TSDF→분류→Roofer→CityJSON→val3dity)

TSDF 10.0 M점(box+buf) → PDAL SMRF+overlay → **ground 1,335,565 · building 1,177,641 · unclassified 7,531,865** →
Roofer → CityJSON → val3dity.

| 산출 | TSDF→Roofer (이번) | ALS→Roofer (P0 canonical, 기준) |
|---|---|---|
| 모델 생성 | **예** | 예 |
| val3dity | **valid** | valid |
| 지붕면 수(RoofSurface) | **32** | **3** |

산출물(gitignore 스크래치): `phases/p0-audit/runs/tum_e2e/DEBY_LOD2_4906972_tsdf_classified.las`,
`…/e2e_4906972.city.json`(+ val3dity report).

**관찰:** TSDF로 **유효(val3dity valid) CityJSON 모델이 실제로 나온다** — 센터로는 막혔던 파이프라인이 표준 depth-융합으로
통과. 단 **지붕면 32개 vs ALS 3개** — TSDF 표면 노이즈(RMS 3.46 m)가 Roofer를 과분할시켜 *위상적으론 유효하나 기하적으로
조각난* 지붕을 만든다. (val3dity는 두께/노이즈에 관대 → "valid"여도 reference의 깔끔한 3면과 다름.)

## 종합 관찰 (판정 금지)

- **방법 탓 vs GS 탓 분리:** 1b의 희박/실패는 *점추출 방법*(Gaussian 센터) 탓 — 표준 depth→TSDF로 **밀도·모델생성 해소**
  (end-to-end 유효 모델 산출). 남는 격차(노이즈→지붕 과분할 32 vs 3)는 *GS depth 품질*(7k vanilla) 탓.
- **TSDF는 센터/바닥 대비 어디:** 밀도는 바닥을 크게 상회, 모델은 나옴 — 그러나 표면 노이즈로 reference 대비 과분할.
  "현 7k-vanilla TSDF가 Roofer-grade(깔끔한 지붕)인가"는 사람 판정. 노이즈를 줄이는 방향(더 긴 반복·기하 prior(L_nc/normal)·
  floater pruning·downscale1 depth)이 reference의 3면에 수렴시키는지는 다음 probe(별도, 사람 판단 후).

## 재현 (EPSG:25832 · 도커 · 엔진 무변경)
```
docker compose run --rm -T dev python scripts/stage2/tum_tsdf_extract.py --downscale 2.0 --voxel 0.05   # 점추출
docker run --rm -v "$PWD":/workspace/JointBuildGS -w /workspace/JointBuildGS jointbuildgs-p0-tools:t0 \
  python3 scripts/stage2/tum_qc_tsdf.py                                                                  # ② 품질
python3 scripts/stage2/tum_roofer_floor.py                                                              # ① 바닥
docker run … jointbuildgs-p0-tools:t0 python3 scripts/stage2/_tsdf_to_classified.py --bid DEBY_LOD2_4906972
# + compose roofer + val3dity on the classified LAS                                                     # ③ end-to-end
```
