# P1-3 — Stage 3 full pipeline with `cluster_primitives_v4`

**Mutual ckpt, 5 representative buildings.** Pipeline: v3/v4 cluster → process_building → CityJSON → val3dity.

v4 parameters are P1-2-fixed (no per-building tuning).

## GT-direct val3dity sanity

Prior result (`results/phase2_ablation_citygml/_gt_direct/summary.json`): **93.9%** (123/131).
GT-direct ≥ 93.9% **GO** (threshold 93.0%).

## Comparison (per spec)

| bid | type | v3 v3d | v4 v3d | v3 height | v4 height | GT height | h_err v4 | coverage v4 |
|---|---|---|---|---|---|---|---|---|
| 0 | tri-slope | ✓ | ✓ | 5.75m | 9.07m | 15.97m | -6.90m | 2.2% |
| 1 | flat | ✓ | ✓ | 2.58m | 4.22m | 16.61m | -12.39m | 2.5% |
| 2 | flat | ✓ | ✗['204'] | 13.95m | 13.95m | 13.63m | +0.31m | 85.2% |
| 6 | hip | ✓ | ✓ | 15.56m | 15.56m | 19.91m | -4.35m | 10.9% |
| 21 | complex | ✓ | ✓ | 2.00m | 3.15m | 17.42m | -14.27m | 0.2% |

## Reference — prior LEGACY baseline (`cluster_primitives` original)

Read from `results/phase2_ablation_citygml/mutual/stage3/stage3_summary.json` (cos_thresh=0.85). Heights unavailable (CityJSON files were not preserved on disk); volume only.

| bid | type | legacy v3d | legacy vol | v4 vol | v4 v3d |
|---|---|---|---|---|---|
| 0 | tri-slope | ✓ | 120.9 | 53.6 | ✓ |
| 1 | flat | ✓ | 1278.3 | 104.0 | ✓ |
| 2 | flat | ✗['203'] | 1339.2 | 1651.7 | ✗['204'] |
| 6 | hip | ✗['203', '203'] | 165.5 | 270.3 | ✓ |
| 21 | complex | ✗['203'] | 49.9 | 5.1 | ✓ |

## GO/NG verdict

| 기준 | 값 | 판정 |
|---|---|---|
| val3dity (≥3/5 pass) | 4/5 | ✓ |
| height (GT±2m, ≥3/5) | 1/5 | ✗ |
| B21 coverage (>50%) | 0.2% | ✗ |
| GT-direct (≥93.0%) | 93.9% | ✓ |

**2/4 criteria → NG** (재검토 필요).

## Diagnosis (NG의 근본 원인)

`process_building`의 `build_convex_polytope`은 **모든 입력 평면을 bounding plane으로 가정**해 half-space intersection을 수행합니다. v4-mode가 한 방향의 wall을 다중 그룹으로 과분리할 경우(예: P1-2 B1 v4=11 walls vs GT 5; P1-3 같은 ckpt 다른 assignment에서 v4=15 walls), 미세하게 어긋난 방향의 평면들이 polytope 내부에서 서로 절단해 안쪽 작은 영역만 남깁니다.

결과: walls 11–15개 중 4–5개만 polytope에 사용되고, vol/height가 GT 대비 크게 작게 나옴. val3dity는 통과되지만 (manifold convex hull 자체는 valid) 의미 있는 건물이 아님.

Legacy `cluster_primitives` (cos_thresh=0.85)는 더 적은 그룹을 만들어 polytope에 적합 — 그래서 위 reference 표에서 legacy vol이 v4 vol보다 큽니다.

**P1-2의 cluster 정확도 향상이 P1-3 Stage 3 전체 성능으로 직접 이어지지 않음** — 다음 단계는 폴리토프 친화적 후처리 (인접 wall merge / area-가중 평균 / top-K) 또는 다른 폴리곤 구성법(2.5D 또는 RANSAC).

## Per-building detail

### B0 (tri-slope)
- v3: val3dity=✓ errs=[], surfaces=6, vol=8.3, h=5.75m (GT 15.97m, Δ-10.22m), cov=0.3%
- v4: val3dity=✓ errs=[], surfaces=9, vol=53.6, h=9.07m (GT 15.97m, Δ-6.90m), cov=2.2%

### B1 (flat)
- v3: val3dity=✓ errs=[], surfaces=5, vol=42.2, h=2.58m (GT 16.61m, Δ-14.03m), cov=1.0%
- v4: val3dity=✓ errs=[], surfaces=9, vol=104.0, h=4.22m (GT 16.61m, Δ-12.39m), cov=2.5%

### B2 (flat)
- v3: val3dity=✓ errs=[], surfaces=10, vol=1991.1, h=13.95m (GT 13.63m, Δ+0.32m), cov=102.7%
- v4: val3dity=✗ errs=['204'], surfaces=8, vol=1651.7, h=13.95m (GT 13.63m, Δ+0.31m), cov=85.2%

### B6 (hip)
- v3: val3dity=✓ errs=[], surfaces=8, vol=90.6, h=15.56m (GT 19.91m, Δ-4.35m), cov=3.7%
- v4: val3dity=✓ errs=[], surfaces=9, vol=270.3, h=15.56m (GT 19.91m, Δ-4.35m), cov=10.9%

### B21 (complex)
- v3: val3dity=✓ errs=[], surfaces=6, vol=1.4, h=2.00m (GT 17.42m, Δ-15.41m), cov=0.1%
- v4: val3dity=✓ errs=[], surfaces=10, vol=5.1, h=3.15m (GT 17.42m, Δ-14.27m), cov=0.2%
