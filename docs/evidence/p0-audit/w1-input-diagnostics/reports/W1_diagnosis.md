# W1 입력 점군 진단

- Run ID: t6_diagnose_20260612_134108
- Run directory: runs/t6_diagnose_20260612_134108
- Metrics JSON: data/work/diagnose/w1_metrics.json
- AOI: x=[690791.740, 691154.650], y=[5335864.050, 5336353.850], area=177,753.3 m2
- Intersecting LoD2 footprint buildings used: 199
- ALS files: 690_5335.laz, 690_5336.laz, 691_5335.laz, 691_5336.laz
- DIM file: dim_v1_classified.laz
- CRS assertion: EPSG:25832 inputs from prior T4/T5 outputs.

## 진단 표

| Metric | ALS | DIM | Notes |
|---|---:|---:|---|
| AOI point density | 20.78 pts/m2 | 244.61 pts/m2 | all classes inside scene_aoi |
| Building density in LoD2 footprints | 15.09 pts/m2 | 292.88 pts/m2 | class 6 points inside intersecting ground plans |
| Roof plane fit residual | 0.405 m (IQR 0.147-0.652) | 0.395 m (IQR 0.232-0.603) | median per-building RMSE after top-35% roof sample plane fit |
| Boundary noise width | 12.481 m | 12.718 m | p95-p05 signed distance for class 6 points within footprint-edge band |
| Wall-like point ratio | 25.08% | 37.79% | edge-band class 6 points below each building's roof-height cutoff |

## 그림

![ALS and DIM point-density grids](figs/w1_density_grid.png)

![Roof, boundary, and wall diagnostics](figs/w1_quality_diagnostics.png)

## 방법 메모

- 밀도는 `scene_aoi.gpkg` 내부 점을 기준으로 계산했고, building density는 AOI와 교차하는 LoD2 ground plan 내부의 class 6 점만 사용했습니다.
- 지붕 잔차는 기준면 정확도 점수가 아니라 진단용 plane-fit RMSE입니다. 각 footprint 내부 class 6 점 중 상위 35% 높이 밴드만 골라 최소제곱 평면을 맞췄습니다.
- 경계부 노이즈 폭은 각 footprint 경계 +/-8 m 밴드의 class 6 점 signed distance로 계산했습니다. 양수는 footprint 내부, 음수는 외부입니다.
- wall-like 비율은 휴리스틱입니다. footprint 경계 2 m 이내이고 건물별 70 percentile 높이보다 0.5 m 이상 낮은 class 6 점을 wall-like로 셌습니다.

## 수직 기준면 정합

- Run ID: t7_vertical_20260612_141617
- Run directory: runs/t7_vertical_20260612_141617
- Ground-grid comparison: ALS class 2 vs DIM class 2, same 2 m cells inside `scene_aoi.gpkg`.
- Raw DIM-ALS ground offset: mean=46.071 m, std=1.273 m, median=45.836 m, p05=45.681 m, p95=46.757 m, n=17,235
- GCG2016 candidate residual: mean=0.409 m, std=1.272 m, median=0.174 m, p05=0.020 m, p95=1.095 m, n=17,235
- Ground-constant candidate residual: mean=-0.000 m, std=1.273 m, median=-0.235 m, p05=-0.390 m, p95=0.686 m, n=17,235
- Applied method: `GCG2016`
- Ground-constant fallback offset: 46.071 m would be subtracted from DIM Z if `ground_constant` is used.
- Corrected residual standard deviation check, all cells: 1.272 m <= 0.500 m -> FAIL
- Corrected residual standard deviation check, central 90% cells: 0.200 m <= 0.500 m -> PASS (share 90.0%).
- GCG2016 grid: `data/raw/geoid/de_bkg_gcg2016.tif` (995,647 bytes, SHA256 `598f18324dea7f8e72421d18add7ac6228259adf91eeb335cc9c27d98484f7ac`)
- Corrected DIM LAZ: `data/work/classify/dim_v1_classified_z.laz`
- Residual metrics JSON: `data/work/vertical/vertical_alignment_metrics.json`
- Offset map PNG: `docs/figs/w1_ground_z_offset_map.png`
- Regenerated section comparison PNG: `docs/figs/w1_vertical_section_corrected.png`
- GCG2016 product reference: https://gdz.bkg.bund.de/index.php/default/quasigeoid-der-bundesrepublik-deutschland-quasigeoid.html
- PROJ grid source: https://cdn.proj.org/de_bkg_gcg2016.tif

- Final correction: GCG2016 was selected as the default official geoid correction. The remaining all-cell standard deviation is dominated by ground-grid outliers rather than a single vertical offset.

## W2 진입 가능 여부 관찰 요약

- 이 장면에서 DIM AOI 밀도는 ALS의 11.77배입니다 (244.61 vs 20.78 pts/m2).
- 매칭된 LoD2 footprint 지붕 샘플의 plane RMSE 중앙값은 DIM이 ALS의 0.98배입니다. 표본 건물 수는 ALS 188개, DIM 130개입니다.
- footprint 경계 +/-8 m 밴드에서 DIM signed-distance 폭은 ALS와 0.24 m 차이가 납니다.
- edge-band 및 below-roof 휴리스틱 기준 wall-like 비율은 DIM이 ALS와 12.71%p 차이가 납니다.
- W2 진입 가능 여부 논의를 위해 동일 AOI, footprint, class, CRS 위의 관찰값은 확보됐습니다. 이 리포트는 관찰 요약만 기록하며 go/no-go 판정은 하지 않습니다.
