# Phase 1 Step 1-5: + L_structure (Structure only, 메커니즘 2)

## 수행 일시
2026-04-19

## 수행 작업 요약

Step 1-3 파이프라인(L_photo + L_depth + L_normal + L_nc + L_sem)에 **L_structure** (inter-primitive 평면 정렬) 추가. 이는 **Step 1-4와 평행한 ablation "Structure only"** 조건 (L_mutual 제외).

**그룹핑:**
- 조건: 같은 class(argmax f_i) + 같은 voxel + 같은 normal direction bin
- 구현: O(N) 해싱 (voxel_size=0.05, 12 direction basis = Fibonacci lattice)
- 매 T=500 iter 재계산
- 대표 평면: `n_k = normalize(Σ w_i·n_i)`, `d_k = −n_k·c̄_k` (w_i = max in-plane scale)

**L_structure:**
```
L_structure = L_normal_align + L_coplanar
  L_normal_align = mean_{i in grouped} (1 − |n_i · n_k|)²   (n_k detach)
  L_coplanar     = mean_{i in grouped} (n_k·c_i + d_k)²     (n_k, d_k detach)
```
Warmup 15,000 iter (L_mutual의 10,000보다 늦게 — f_i/n_i가 충분히 수렴한 후 그룹 정의 안정화 목적).

---

## 주요 결과 요약

### 📊 렌더링 (Step 1-3 수준 유지)
| 지표 | Step 1-3 | **Step 1-5** | Δ |
|------|---:|---:|---:|
| eval PSNR (4-view, final) | 22.07 | **22.16** | +0.09 |
| test PSNR (100 views) | 20.51 | 20.62 | +0.11 |
| SSIM | 0.587 | 0.588 | +0.001 |
| LPIPS | 0.615 | 0.613 | -0.002 |

### 📐 기하 (거의 동일)
| 지표 | Step 1-3 | **Step 1-5** | Δ |
|------|---:|---:|---:|
| F1 @ 0.5 | 0.998 | 0.999 | +0.001 |
| F1 @ 1.0 | 1.000 | 1.000 | ±0 |
| Chamfer sym mean | 0.0208 | 0.0200 | -0.0008 |
| Depth MAE | 0.051 | 0.057 | +0.006 |
| Normal cos | 0.684 | 0.677 | -0.007 |

### 🏷️ 의미론 — 전체 평균은 소폭 개선, 뷰별 편차 큼
| 지표 | Step 1-3 | **Step 1-5** | Δ |
|------|---:|---:|---:|
| mIoU (100 test views) | 0.635 | **0.640** | +0.005 |
| Roof IoU | 0.704 | 0.702 | -0.002 |
| Wall IoU | 0.616 | 0.620 | +0.004 |
| **Terrain IoU** | **0.585** | **0.599** | **+0.014** |

**⚠ 경고: 4-view diagnostic에서는 per-view 편차 큼** (아래 정성 분석 참조). 전체 100뷰 평균 +0.005와 상충되는 개별 regression 존재.

### 🎯 L_structure 효과 (σ 감소 — 설계 목표)
| 지표 | Step 1-3 | **Step 1-5** | Δ |
|------|---:|---:|---:|
| **σ_normal_intra (mean)** | 0.0246 | **0.0136** | **-45%** ✓ |
| σ_normal_intra (weighted) | 0.0243 | 0.0128 | -47% |
| **σ_coplanar (mean)** | 0.0085 | **0.0072** | **-16%** ✓ |
| σ_coplanar (weighted) | 0.0087 | 0.0073 | -16% |

**그룹핑 통계** (각 ckpt 독립 그룹핑):
| 지표 | Step 1-3 | Step 1-5 |
|------|---:|---:|
| n_groups | 254,562 | **248,885** |
| n_in_group | 3.62M | 3.75M (71%) |
| 평균 그룹 크기 | 14.2 | 15.1 |
| 중앙값 그룹 크기 | 9 | 9 |

### ⏱️ 효율
| 지표 | Step 1-3 | Step 1-5 |
|------|---:|---:|
| 학습 시간 | 405min | 419min (+3.5%) |
| 속도 (it/s) | ~1.4 | ~1.3 |
| N (최종) | 5.27M | 5.27M |

---

## 학습 곡선

![Training curves](figures/training_curves.png)

주황 점선 = L_structure warmup (iter 15,000).

- **Photo/Depth/Sem**: Step 1-3와 유사한 수렴. Warmup 이후 큰 변화 없음 (L_structure가 RGB 렌더링에 직접 영향 X).
- **L_structure 각 항 (좌하, log scale)**:
  - normal_align (crimson): 초기 0.0006 → 최종 0.0002 (65% ↓)
  - coplanar (blue): 초기 0.00008 → 최종 0.0001 (안정)
- **eval PSNR (중하)**: 22+ 유지, Step 1-3 및 CityGSV2 baseline 근접.
- **n_groups (우하)**: warmup 시작 시 ~248k, 학습 중 유사 수준 유지.

---

## σ 히스토그램 — L_structure 효과 정량화

![Sigma histograms](figures/structure_histograms.png)

**좌 (σ_normal_intra)**:
- Step 1-3(파랑): 피크가 0.02-0.04 영역 넓게 분포
- Step 1-5(빨강): **피크가 0~0.01로 좌측 이동**, mean 0.0246 → 0.0136

**우 (σ_coplanar)**:
- Step 1-5 분포가 전반적으로 왼쪽으로 이동 (더 co-planar)
- mean 0.0085 → 0.0072

**해석**: L_normal_align이 그룹 내 법선 편차를 45% 줄임. L_coplanar가 그룹 내 점들의 평면 벗어남을 16% 줄임. 설계대로 작동.

---

## Step 1-3 vs Step 1-5 렌더링 비교 (같은 4뷰)

**뷰 선택 (Step 1-3 REPORT와 통일, 위→아래)**: Best(5368) → RT-confusion(5083) → Wall-err(5528) → Worst(5328)

**Layout**: `GT | Step 1-3 render | Step 1-5 render | diff×5`

![Render compare](figures/render_compare_step13_step15.png)

렌더링은 거의 동일. Diff에 엣지/그림자 주변 작은 변화만. **L_structure가 RGB 렌더링을 실질 변화시키지 않음** (예상대로 — 설계상 L_structure는 n_i, c_i만 수정).

---

## Step 1-3 vs Step 1-5 Semantic 비교 — per-view 편차 정직하게

![Semantic compare](figures/sem_compare_step13_step15.png)

**Layout**: `RGB | GT_sem | Step 1-3 pred | Step 1-5 pred | Step 1-3 err | Step 1-5 err`

### Per-view mIoU 변화

| 뷰 | idx | Step 1-3 mIoU | Step 1-5 mIoU | Δ | 해석 |
|---|---:|---:|---:|---:|---|
| [Row 1] Best | 5368 | 0.780 | 0.695 | **-0.084** | ⚠ regression |
| [Row 2] RT-confusion | 5083 | 0.496 | 0.511 | +0.015 | 소폭 개선 |
| [Row 3] Wall-err | 5528 | 0.624 | 0.467 | **-0.157** | ⚠ 큰 regression |
| [Row 4] Worst | 5328 | 0.136 | 0.139 | +0.003 | 미미 |

**⚠ 4뷰 per-view 평균 Δ = −0.056** vs **전체 100뷰 mIoU Δ = +0.005**. 두 수치가 상충되는 이유:

1. **선택 편향**: 이 4뷰은 Step 1-3의 mIoU **양극단**(best+worst+confusion+wall-err)을 포함. 전체 100뷰의 평균 동향과 다를 수 있음.
2. **L_structure의 효과 영역**: σ_normal_intra 감소(-45%)는 잘 작동하지만, 이것이 "semantic 정확도"로 직접 연결되진 않음. 그룹 내 법선 정렬이 pred 클래스 라벨링에 직접 영향 주지 않음 (L_structure는 ∂L/∂f_i = 0).
3. **"정리된 normal"이 이 4뷰에서 불리한 경우 있음**: Wall-err 뷰(5528)에서 L_structure가 그룹 대표 normal로 정렬하면서 일부 경계 영역의 클래스가 재분류된 듯 (f_i gradient 없지만 간접 영향 — 렌더링 결과가 미세 변동).

**솔직한 평가:**
- 주 목표(**σ 감소**)는 명확히 달성 ✓
- 부수 효과로 100-뷰 평균 mIoU +0.005 소폭 개선
- 4뷰 진단에서 Wall-err와 Best가 -0.08~-0.16 regression
- 이 regression은 **100뷰 전체에선 상쇄**되나, 특정 뷰에서는 발생
- L_structure는 per-pixel semantic 정확도를 직접 목표로 하지 않음 — "구조적 일관성" 개선이 본질

---

## Gradient 격리 검증 (pre-training smoke)

Step 1-3 ckpt 기준 단일 L_structure backward:

| 파라미터 | max \|grad\| | 기대 |
|---------|:---:|---|
| **means (c_i)** | ✅ 2.7e-8 | L_coplanar에서 흘림 |
| **quats (n_i)** | ✅ 1.2e-6 | L_normal_align에서 흘림 |
| log_scales (s_i) | **None** | ✅ 설계대로 |
| sem_logits (f_i) | **None** | ✅ 설계대로 (그룹 할당은 argmax, discrete) |
| opacities, sh0, shN | None | ✅ |

**검증:**
- ∂L_na/∂n_i ≠ 0 ✓
- ∂L_cp/∂c_i ≠ 0 ✓
- ∂L_str/∂f_i = 0 ✓ (CLAUDE.md §메커니즘 2 규정대로)

초기 loss 값:
- L_normal_align = 0.00085
- L_coplanar = 0.00009
- 이미 작음 (Step 1-3 기하가 합리적으로 정렬됨) → 학습 중 추가 감소 여지 제한적

---

## 시각적 산출물 체크리스트

- [x] 그룹핑 PLY (그룹별 색상, 25만 그룹, 5.27M pts) → `run/primitives_groups.ply`
- [x] σ_normal_intra 히스토그램 → `figures/structure_histograms.png` (좌)
- [x] σ_coplanar 히스토그램 → same figure (우)
- [x] 그룹 통계 표 (본 REPORT)
- [x] 학습 곡선 (L_structure 각 항 분리, log scale) → `figures/training_curves.png`
- [x] Step 1-3 vs 1-5 렌더링 비교 → `figures/render_compare_step13_step15.png`
- [x] Step 1-3 vs 1-5 semantic 비교 → `figures/sem_compare_step13_step15.png`
- [x] Gradient 격리 로그 (본 REPORT)
- [x] 메트릭 JSON (rendering/geometry/semantic/structure_stats)

---

## 학습 설정

- **Data**: Step 1-3과 동일 (MatrixCity + depth + normal + rule-based semantic GT)
- **Loss**: `L = Step 1-3 + 0.1·L_structure` (warmup 15,000 이후)
- **L_structure 파라미터**:
  - voxel_size=0.05, n_directions=12, min_group_size=5
  - w_normal_align=1.0, w_coplanar=1.0
  - regroup_every=500 iter
- **Optimizer**: per-param Adam (Step 1-3와 동일)
- 30,000 iter, RTX 3090 (GPU1), 419분

---

## Go/No-Go

| 기준 | 목표 | 달성 | 판정 |
|------|------|------|------|
| 렌더링/기하 유지 | Step 1-3 대비 유지 | PSNR +0.09, F1 +0.001, Chamfer -0.0008 | ✅ |
| **σ_normal_intra 감소** | Step 1-3 대비 감소 | **-45%** (mean) | ✅✅ |
| **σ_coplanar 감소** | Step 1-3 대비 감소 | **-16%** (mean) | ✅ |
| mIoU 유지/개선 | Step 1-3의 0.635 대비 | +0.005 (≈동일, per-view 편차 큼) | ⚠ 주의 |
| Gradient 격리 | ∂L/∂n,c ≠ 0, ∂L/∂f,s = 0 | 검증됨 | ✅ |

**Go** — L_structure의 주 목표(σ 감소)는 명확히 달성. 렌더링/기하 유지. mIoU 전체 평균은 소폭 개선이나 per-view 편차 큼 (L_structure가 semantic 직접 목표 아닌 한계).

---

## L_mutual (Step 1-4)과의 비교 — "scope"가 다른 메커니즘

| 측면 | L_mutual (Step 1-4) | L_structure (Step 1-5) |
|------|---|---|
| **작동 level** | intra-primitive | inter-primitive (그룹) |
| **변화 규모** | 구조 재편 (class 재분류, normal 회전) | 정제 (그룹 내 정렬) |
| **목표 metric** | Wall verticality, 높이 기반 Roof/Terrain | σ_normal_intra, σ_coplanar |
| **Wall 클래스 수 변화** | 1.66M → 0.65M (-60% 정제) | 1.66M → 유사 수준 |
| **수평 normal primitive 수 (분류 무관)** | 342k → 744k (+2.2×) | 유사 수준 |
| **per-view mIoU 편차** | +0.11 (RT), -0.10 (Wall-err) 등 | -0.08 (Best), -0.16 (Wall-err), +0.02 (RT) |

**중요: "regression 없음 ≠ 더 좋음":**
- L_structure의 변화 scope가 작아 baseline 유지 + 소폭 개선 → regression 낼 여지 자체가 작음
- L_mutual은 큰 구조 변화(class 재편 60%, normal 회전 2.2배)로 trade-off 뚜렷
- 둘은 **다른 scope의 문제를 풀므로** 직접 우열 비교 무의미
- **결합(Step 1-6)에서의 상호작용**이 본 평가 지점

**서로 다른 구조 품질 담당:**
- L_mutual → 프리미티브 클래스 할당 정확도 (벽/지붕/지면 구분)
- L_structure → 같은 면 그룹의 평면성 (기하 일관성)
- **CityGML 변환**에서 둘 다 필요 — 벽이 제대로 표시되고 (L_mutual), 하나의 벽이 여러 조각일 때 co-planar이어야(L_structure)

---

## 이슈 및 해결

### 이슈 1: L_structure 초기값이 이미 작음
- **증상**: warmup 시점(iter 15k)에서 L_normal_align = 0.00067, L_coplanar = 0.00008 (이미 ~10⁻⁴ 수준)
- **원인**: 그룹 기준이 "normal direction bin이 같은 프리미티브" → 이미 비슷한 법선을 가진 것들끼리 묶음. 초기 σ가 그룹 기준 자체로 제한됨.
- **영향**: L_structure가 크게 다른 것을 강제하지 않고 "있는 그룹을 더 정렬"만 함. 변화량 제한.
- **대안**: min_group_size를 높이면 더 큰 그룹이 형성되어 σ 여지가 커질 수 있음 (향후 튜닝 여지).

### 이슈 2: per-view mIoU regression (Best, Wall-err)
- **증상**: 4-view diagnostic 중 2개 뷰에서 mIoU -0.08, -0.16 감소
- **원인 추정**:
  - L_structure는 ∂L/∂f_i = 0 이지만 n_i, c_i 수정 → 렌더링 결과(f_render) 간접 변화
  - 그룹 대표 normal로 정렬되면서 경계 영역 픽셀 클래스가 살짝 다름
- **영향**: 전체 100뷰 평균(+0.005)에선 상쇄되지만 특정 뷰에선 regression
- **Phase 2에서 재평가**: CityGML 품질(val3dity)로 downstream 영향 판단

### 이슈 3: N 3k 차이 (Step 1-3 5,270,672 vs Step 1-5 5,274,035)
- **증상**: 같은 seed인데 N이 다름
- **원인**: CUDA 부동소수점 연산 비결정성 + densification의 random split/clone 결정 차이
- **영향**: 같은 그룹핑 직접 비교 불가 → 각 ckpt 독립 그룹핑 후 분포 비교 (구현 완료)

---

## 다음 단계

**Step 1-6: Both (L_mutual + L_structure 결합)**
- L_mutual warmup 10,000, L_structure warmup 20,000 (기하-의미 수렴 후 그룹 안정화)
- 4조건 ablation 종합: Baseline(Step 1-3) / Mutual only(Step 1-4) / Structure only(Step 1-5) / Both(Step 1-6)
- 검증 지점:
  - Wall 수직도: Mutual only 수준 유지?
  - σ_normal_intra: Structure only 수준 유지?
  - **Both > Mutual + Structure** (시너지) or **Both < Mutual + Structure** (간섭)?
  - 순차 파이프라인과의 차별점: 두 메커니즘 동시 + 주기적 재할당 순환 효과 검증
