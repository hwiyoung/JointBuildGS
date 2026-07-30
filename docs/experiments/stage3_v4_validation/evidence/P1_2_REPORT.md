# P1-2 — `cluster_primitives_v4` (mode) Generalization Test

**5 buildings × 2 conditions, FIXED parameters.** GT is used for evaluation only (never as algorithm input).

Selected buildings (one per GT type): B0 tri-slope, B1 flat, B3 complex, B5 hip, B8 gable.

## Fixed parameters

```
gravity = [0, 1, 0]
wall_vert_thresh = 0.15
az_bin = 3°, smoothing σ = 2 bins, prominence = 10% of max
az_min_peak_dist = 20°, az_assign_max_dist = 25°
plane_d_bin = 0.1 m, plane_d_smooth_σ = 2 bins, prominence = 10%
plane_d_min_dist = 0.4 m, plane_d_assign_max = 0.5 m
component_dist = 2.0 m  (P1-1b sweep showed 0.5 → 87 walls; 2.0 → 9)
```

## Table 1 — Overall comparison

| bid | type | cond | v3 walls | v4-db walls | v4-mode walls | v4-mode roofs | total | max_wall% | noise% |
|---|---|---|---|---|---|---|---|---|---|
| 0 | tri-slope | baseline | 3 | 7 | **19** | 4 | 23 | 14.1% | 33.7% |
| 0 | tri-slope | mutual | 2 | 2 | **9** | 7 | 16 | 23.2% | 40.1% |
| 1 | flat | baseline | 9 | 5 | **24** | 5 | 29 | 17.6% | 38.8% |
| 1 | flat | mutual | 3 | 1 | **11** | 6 | 17 | 33.7% | 39.7% |
| 3 | complex | baseline | 27 | 8 | **31** | 12 | 43 | 7.7% | 26.5% |
| 3 | complex | mutual | 16 | 14 | **14** | 9 | 23 | 16.3% | 27.7% |
| 5 | hip | baseline | 10 | 8 | **27** | 6 | 33 | 8.1% | 35.8% |
| 5 | hip | mutual | 5 | 5 | **9** | 11 | 20 | 14.1% | 33.4% |
| 8 | gable | baseline | 4 | 4 | **11** | 4 | 15 | 11.8% | 24.9% |
| 8 | gable | mutual | 7 | 3 | **4** | 3 | 7 | 24.3% | 29.0% |

## Table 2 — Wall-only metrics (v4-mode)

| bid | cond | GT main dirs | v4 wall groups | ±2? | wall match (cos>0.95) | wall purity (\|n·target\|≥0.94) | wall coverage |
|---|---|---|---|---|---|---|---|
| 0 | baseline | 10 | 19 | ✗ | 79% | 67% | 69% |
| 0 | mutual | 10 | 9 | ✓ | 100% | 93% | 61% |
| 1 | baseline | 5 | 24 | ✗ | 92% | 79% | 74% |
| 1 | mutual | 5 | 11 | ✗ | 100% | 95% | 76% |
| 3 | baseline | 15 | 31 | ✗ | 84% | 73% | 59% |
| 3 | mutual | 15 | 14 | ✓ | 100% | 96% | 54% |
| 5 | baseline | 11 | 27 | ✗ | 81% | 78% | 63% |
| 5 | mutual | 11 | 9 | ✓ | 100% | 89% | 61% |
| 8 | baseline | 4 | 11 | ✗ | 82% | 80% | 77% |
| 8 | mutual | 4 | 4 | ✓ | 100% | 98% | 71% |

## Table 3 — Roof-only metrics (v4-mode)

| bid | cond | GT roof faces | v4 roof groups | roof match (cos>0.95) | roof purity |
|---|---|---|---|---|---|
| 0 | baseline | 3 | 4 | 25% | 19% |
| 0 | mutual | 3 | 7 | 29% | 26% |
| 1 | baseline | 1 | 5 | 20% | 28% |
| 1 | mutual | 1 | 6 | 17% | 27% |
| 3 | baseline | 25 | 12 | 42% | 32% |
| 3 | mutual | 25 | 9 | 56% | 44% |
| 5 | baseline | 4 | 6 | 67% | 62% |
| 5 | mutual | 4 | 11 | 45% | 42% |
| 8 | baseline | 2 | 4 | 25% | 46% |
| 8 | mutual | 2 | 3 | 33% | 63% |

## Table 4 — v4-mode vs v4-dbscan

| bid | cond | v4-db walls | v4-mode walls | wall ↑? | v4-db max% | v4-mode max% | max% ↓? |
|---|---|---|---|---|---|---|---|
| 0 | baseline | 7 | 19 | ✓ | 48% | 14% | ✓ |
| 0 | mutual | 2 | 9 | ✓ | 90% | 23% | ✓ |
| 1 | baseline | 5 | 24 | ✓ | 33% | 18% | ✓ |
| 1 | mutual | 1 | 11 | ✓ | 93% | 34% | ✓ |
| 3 | baseline | 8 | 31 | ✓ | 14% | 8% | ✓ |
| 3 | mutual | 14 | 14 | = | 44% | 16% | ✓ |
| 5 | baseline | 8 | 27 | ✓ | 18% | 8% | ✓ |
| 5 | mutual | 5 | 9 | ✓ | 35% | 14% | ✓ |
| 8 | baseline | 4 | 11 | ✓ | 12% | 12% | ✗ |
| 8 | mutual | 3 | 4 | ✓ | 64% | 24% | ✓ |

## GO/NG verdict (Mutual; GT-correspondence)

| bid | type | walls±2? | match >70%? | purity >70%? | v4-db ↑? | verdict |
|---|---|---|---|---|---|---|
| 0 | tri-slope | ✓ | ✓ | ✓ | ✓ | **GO** |
| 1 | flat | ✗ | ✓ | ✓ | ✓ | **NG** |
| 3 | complex | ✓ | ✓ | ✓ | ✓ | **GO** |
| 5 | hip | ✓ | ✓ | ✓ | ✓ | **GO** |
| 8 | gable | ✓ | ✓ | ✓ | ✓ | **GO** |

**Mutual 4/5 GO** → **P1-3 진행**.

## 실패 건물 원인 기록 (수정 없음 — 기록만)

### B1 (flat)
- [x] azimuth peak 과다
- [x] roof matching 낮음 (17%)

## 관찰

- **chaining 해결 일관성**: Mutual 모든 건물에서 v4-mode max_wall% < v4-dbscan max_wall%. 적도 chaining 본질적 해결.
- **roof은 v4와 무관** (v3 path 그대로). roof matching/purity가 낮은 건 학습 측 약점.
- **baseline은 prim wall vert 낮아 non-vert 분기로 fallback** → wall groups 인플레.