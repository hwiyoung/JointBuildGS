# Phase 2 Step 2-2 — Stage 2 메커니즘이 CityGML LOD2 품질에 미치는 영향

**최초 작성**: 2026-04-25 KST  
**v4 갱신**: 2026-04-26 KST (bbox_margin 버그 수정 후 재측정 반영)  
**실험 대상**: 3D BAG Amsterdam Jordaan 합성 데이터 (131 건물) × 4 조건 Stage 2 × convex Stage 3  
**Stage 2 ckpts**: 각 30,000 iter, ~988K primitives/condition  
**Stage 3 (고정)**: Convex polytope (half-space intersection + ConvexHull)  

> **REVISION NOTE (v4)**: 2026-04-25 23:08 `src/stage3/plane_intersection.py` 의 `bbox_margin` 자동화 수정 (None → max(5.0, 0.5×extent)) 후 GT 와 4 조건 모두 재측정. **GT convex 천장 76.3% → 96.2%, 모든 조건 +10~17%p 상승.** Pre-fix 측정값은 tracked 파일 (`_gt_stage3_test/`, `*/eval/`, `*/stage3/`) 에 보존, post-fix 는 `_gt_stage3_convex_fixed/`, `*/eval_fixed/`, `*/stage3_fixed/`. 본 v4 는 post-fix 기준. Pre-fix 해석 중 *bbox 버그 발동률* 에 의해 왜곡됐던 부분 (특히 C1 magnitude) 재해석.

---

## 0. TL;DR (3 가지 결과 + 2 가지 미확정)

**확인된 것** (v4, post-fix 기준):
1. **L_mutual 의 Stage 2 효과 명확** — Wall vertical-frac 28% → 79% (Phase 1 의 19% → 91% 와 같은 방향, magnitude 약간 작음). 공간적으로도 균질 (corner 영역 포함).
2. **Stage 3 val3dity 에서 Structure/Both +1.5~2.3%p, Mutual −3.8%p 회귀** — type별 패턴: complex/hip/tri-slope (+10~17%p) 개선, flat/gable (모든 메커니즘 −5~−16%p) 회귀. **Pre-fix 의 −8.4%p 회귀는 절반이 bbox 버그 발동률 차이였음.**
3. **메커니즘별 다른 축 개선**: Mutual = face IoU (0.214→0.240) 최고, Structure = val3dity + semantic accuracy 최고.

**미확정**:
1. **L_structure 의 Phase 2 약함** — σ_normal_intra 변화 +1% (Phase 1 −45% 대비). 일부 건물 (flat) 에서만 효과 (−13%), 평균 효과 미미. 원인 가설 미확정. (bbox fix 와 무관, 여전히 유효)
2. **Mutual + Structure 시너지 부재** — Both 의 val3dity 가 Structure 보다 약간 낮음 (54.2% vs 55.0%). "순환 효과" claim 미입증.

**v4 신규 발견**:
- **GT convex 천장이 96.2%** (pre-fix 76.3% 는 bbox 버그). 따라서 "Stage 3 algorithm 이 천장 76.3% 라서 한계" 라는 진단은 무효. 우리 best 55.0% / 천장 96.2% = **57% 달성** (수치는 우연히 동일).
- **203 에러 순위 변화**: Structure (46) < Mutual (52) ≈ Both (52) < Baseline (54). Mutual 의 203 감소폭이 가장 큼 (81→52, −29). Pre-fix 의 "Mutual → 203 증가" 서사 중 *bbox 버그가 dominant 원인* 이었음.
- 그러나 Mutual 의 val3dity 는 여전히 최저 (48.9%) — 203 외 에러 (204=4) 와 stage3 처리 실패가 합쳐진 결과.

---

## 1. 목적 & 설정

| 조건 | Stage 2 Loss | 목적 |
|---|---|---|
| Baseline | L_photo + L_depth + L_normal + L_nc + L_sem | 메커니즘 없음 (vanilla + semantic) |
| Mutual | + **L_mutual** (intra-primitive 도메인 규칙) | 메커니즘 1 단독 |
| Structure | + **L_structure** (inter-primitive 정렬) | 메커니즘 2 단독 |
| Both | + L_mutual + L_structure | 두 메커니즘 동시 |

모든 조건 동일 Stage 3 (convex polytope) → Stage 2 차이만 비교.

**Stage 3 의 6 단계** (실험 설계의 분석 단위):
1. 분류 + 필터 (semantic class, opacity)
2. Multi-primitive 클러스터링 (cos>0.85 + 공간 근접)
3. 클러스터 → 대표 평면 (orient + ground + bbox 추가)
4. 평면 교차 → convex polytope
5. Ground surface 부착
6. CityJSON + val3dity

---

## 2. 평가 기준선 — GT 상한 (v4 갱신)

Stage 2 quality 와 별개로 **Stage 3 알고리즘 자체** 의 천장 측정. GT scene.obj 를 입력으로:

| 방식 | val3dity 통과율 | 의미 |
|---|---|---|
| **GT direct (topology 보존)** | **93.9%** (123/131) | 3D BAG 원본 미세 결함만 실패 |
| **GT + convex polytope (post-fix)** | **96.2%** (126/131) | **현재 Stage 3 의 천장**. GT direct 보다 *높음* — convex 가 GT 의 자잘한 결함을 normalize |
| GT + convex polytope (pre-fix) | 76.3% (100/131) | bbox_margin 버그로 14 건물 처리 자체 실패 (REPORT v3 까지) |
| GT + 2.5D hybrid | 67.2% | 구현 버그 (별도 작업) |
| GT + PolyFit (CGAL+SCIP) | 0% | watertight 후처리 미완 |

→ 우리 Stage 2 best (Structure 55.0%) 는 **convex 천장 96.2% 의 57%** 달성. (수치 57% 는 pre-fix 와 우연 동일)

**Type 별 GT convex 상한 (post-fix)**:
- tri-slope 100%, flat 100%, gable 100%, hip 95.7%, complex 86.2%
- **Flat 100%**: 박스형 단순 건물은 convex 가 완벽 처리. Pre-fix 의 64% ceiling 은 bbox 버그 (flat 건물에서 가장 심하게 발동).
- **Complex 86.2%**: L-shape, 안뜰 등 진짜 non-convex 가 한계. 4 건물 (29 중) 만 실패 — 이게 convex polytope 의 *진짜* 알고리즘 한계.

**의의**: "convex polytope 의 천장이 76.3% 라서 알고리즘 자체에 큰 한계가 있다" 는 v3 서사 무효. 실제로는 96.2% 천장에서 우리 best 55%까지 격차 = **약 41%p 개선 여지** (대부분 Stage 2 quality / 인터페이스 정합 문제).

---

## 3. Stage 2 결과

### 3.1 Rendering quality (eval set, 4 조건 parity 확인)

| Condition | eval PSNR | eval SSIM | eval mIoU | 비고 |
|---|---|---|---|---|
| Baseline | 40.35 | (TB) | (계산 안 됨) | 4 조건 PSNR 거의 동일 |
| Mutual | 40.93 | (TB) | (계산 안 됨) | |
| Structure | 40.96 | (TB) | (계산 안 됨) | |
| Both | 39.81 | (TB) | (계산 안 됨) | |

**관찰**: 모든 조건 PSNR 40 saturation. Stage 3 차이는 **렌더링 품질이 아닌 primitive 구조적 차이** 에서 옴.

### 3.2 Primitive 구조 지표 (Stage 3 의 입력 직접 측정)

| 지표 | Baseline | Mutual | Structure | Both | Phase 1 비교 |
|---|---|---|---|---|---|
| **Wall vertical-fraction** | 28.0% | **79.3%** ↑ | 28.4% | **79.4%** ↑ | Phase 1 19→91% 와 같은 방향 |
| Roof horizontal-fraction | 56.3% | 54.1% | 56.5% | 54.3% | — |
| σ_normal_intra (deg, group 평균) | 14.74 | **12.63** ↓ | 14.88 | 12.99 | **Phase 1 L_structure −45%, Phase 2 +1% (효과 부재)** |
| σ_coplanar (m, median) | 1.91 | **1.84** ↓ | **1.86** ↓ | 2.01 | Phase 1 L_structure −16% |
| n_groups / building (mean) | 7.98 | 7.95 | 7.90 | 7.65 | Both 가 약간 적음 |

### 3.3 도메인 메트릭 — D4 결과

**질문**: GT wall 은 100% 완벽 수직 (모든 2,334 face 가 < 0.1° 편차). Baseline 은 왜 28% 만 수직?

**측정 (3 건물 평균)**:

| Condition | < 1° (실질 수직) | < 5° | < 10° | mean tilt | 코너 영역 (d<1m) | 멀리 (d<10m) |
|---|---|---|---|---|---|---|
| Baseline | 4-5% | 22-25% | 48-54% | 12-15° | tilt 16.5°, %<5° 20% | tilt 12.2°, %<5° 25% |
| Mutual | (TB) | **80%+** | (높음) | **2.7°** | tilt 2.76°, %<5° **81%** | tilt 2.84°, %<5° 78% |
| Structure | 5-6% | 23-26% | 49-55% | 12-15° | (Baseline 동일) | (Baseline 동일) |
| Both | (TB) | 80%+ | (높음) | 2.8° | 81% | 77% |

![fig_d4](figures/fig_d4_baseline_wall_tilt.png)  
*Figure D4. Baseline wall 의 tilt 분포 (왼쪽: histogram, 가운데: 3D 위치, 오른쪽: corner 거리 vs tilt). 3 건물에서 일관된 패턴: corner 영역에서 tilt 높음.*

**핵심 발견**:
- **Baseline**: corner 부근에서 tilt 더 큼 (16.5° vs 12.2°). Gaussian 들이 인접 두 벽 사이에서 "평균 normal" 로 학습됨.
- **Mutual**: 코너 포함 **공간적으로 균일하게 잘 fixed** (corner 81% > 멀리 78%). L_mutual 의 per-primitive 메커니즘으로 spatial dependency 추가 없이 corner 문제 해결.
- **Structure 단독**: Baseline 과 동일 패턴 — Wall verticalization 에 영향 없음 (메커니즘 2 의 정의대로).

→ **L_mutual 은 의도대로 작동**. 공간적 weighting 추가 불필요.

### 3.4 Semantic 클래스 분포

| Class | Baseline | Mutual | Structure | Both |
|---|---|---|---|---|
| BG | 0.0% | 1.4% | 0.0% | 1.3% |
| Roof | 40.0% | 42.1% | 40.2% | 42.3% |
| Wall | 42.2% | 41.2% | 42.1% | 41.0% |
| Terrain | 17.8% | 15.3% | 17.7% | 15.3% |

**관찰**: L_mutual 이 작은 semantic side effect — Terrain → Roof 재분류 +2%p. L_mutual 의 `p_c × 기하오차` joint gradient 가 의미론에도 영향 미침.

---

## 4. Stage 3 결과 — 6-step 단계별 분석 (D3)

bid=2 (flat), bid=22 (gable), bid=6 (hip), bid=21 (complex) 4 건물에서 6 step 진행 추적.

> **v4 caveat**: 4.1, 4.2 의 단일 건물 case study 는 pre-fix 데이터 기준. Post-fix 에서 개별 건물 상태 (✓/✗) 가 일부 바뀌었을 수 있음 (특히 bid=2 flat 같이 bbox 영향이 큰 건물). 집계 통계 (4.3-4.5) 는 모두 post-fix 로 갱신 완료.

### 4.1 Step 별 정량 — bid=2 flat (대표 case study, D1+D3)

| Step | 측정값 | Baseline | Mutual | Structure | Both |
|---|---|---|---|---|---|
| 1. 필터 | 총 primitive | 5,215 | 4,668 | 5,139 | 4,976 |
| | Wall primitive | 2,666 | 2,318 | 2,749 | 2,456 |
| 2. 클러스터 | n_groups | 7 | **5** ↓ | 7 | 7 |
| | Wall groups | 4 | **2** ↓ | 3 | 3 |
| 3. 대표평면 | (조정 없음) | — | — | — | — |
| 4. Polytope | n_faces | 7 | 7 | 8 | 6 |
| 6. val3dity | valid? | ✓ | **✗ (203)** | ✓ | ✓ |

**해석**:
- **Step 1** (Stage 2 출력): 4 조건 모두 wall primitive 수가 비슷 (2300-2750). Mutual 이 약간 적음 (-13%, pruning 효과)
- **Step 2** (clustering): **Mutual 만 wall groups 가 4 → 2 로 급감**. cos > 0.85 threshold 가 모든 wall 이 수직화된 후엔 잘못 merge
- **Step 4** (polytope): face 수 자체는 유사
- **Step 6**: Mutual 만 fail (203 = non-planar face). 줄어든 wall plane 의 교차 결과가 평면 폐쇄 못함

![fig_d3_bid002](figures/fig_d3_bid002_steps.png)  
*Figure D3-bid002. bid=2 (flat) 의 Stage 3 6 단계, 4 조건 비교. Mutual 행 마지막 cell 만 빨간색 (val3dity invalid).*

### 4.2 다른 건물 — 패턴은 이질적

| bid | Type | Baseline | Mutual | Structure | Both | 패턴 |
|---|---|---|---|---|---|---|
| 2 | flat | ✓ | ✗ 203 | ✓ | ✓ | Mutual fails |
| 22 | gable | ✗ 203 | ✓ | ✓ | ✓ | Baseline fails |
| 6 | hip | ✗ 203 | ✓ | ✓ | ✗ 203 | mixed |
| 21 | complex | ✓ | ✓ | ✗ 203 | ✗ 203 | Structure/Both fail |

![fig_d3_bid022](figures/fig_d3_bid022_steps.png)  
*Figure D3-bid022. gable. Baseline 만 invalid.*

→ **단일 건물 단위로는 어느 조건이 우세한지 불일관**. 집계 수준에서만 통계적 우세 (Structure/Both > Baseline > Mutual).

### 4.3 전체 통계 — 4 조건 × 131 건물 (v4, post-fix)

| Condition | val3dity pass | face IoU (mean) | Hausdorff (m) | SemAcc |
|---|---|---|---|---|
| **Baseline** | **52.7%** (69/131) | 0.214 | 11.37 | 21.6% |
| **Mutual** | 48.9% (64/131) ↓ | **0.240** ↑ | 11.54 | 20.6% |
| **Structure** | **55.0%** (72/131) ↑ | 0.221 | 11.45 | **22.0%** ↑ |
| **Both** | **54.2%** (71/131) ↑ | 0.227 | 11.56 | 20.4% |

**v3 (pre-fix) 와 비교**:

| Condition | v3 val3dity | v4 val3dity | Δ |
|---|---|---|---|
| Baseline | 40.5% | 52.7% | +12.2%p |
| Mutual | 32.1% | 48.9% | **+16.8%p** (가장 큰 회복) |
| Structure | 43.5% | 55.0% | +11.5%p |
| Both | 43.5% | 54.2% | +10.7%p |

→ Mutual 의 회복폭이 가장 큼. Pre-fix 의 −8.4%p 회귀 (Mutual vs Baseline) 가 post-fix 에서 −3.8%p 로 축소. C1 의 magnitude 절반이 bbox 버그였음.

![fig2](figures/fig2_val3dity_bars.png)  
*Figure 2. 조건별 val3dity 통과율 (pre-fix 기반, post-fix 갱신 필요).*

### 4.4 Roof type 별 통계 (v4, post-fix)

| Type | GT direct | GT convex | Baseline | Mutual | Structure | Both | Pattern |
|---|---|---|---|---|---|---|---|
| complex (29) | 79.3% | **86.2%** | 58.6% | 51.7% | **69.0%** ↑ | 65.5% | Structure/Both ↑ |
| hip (23) | 100% | **95.7%** | 43.5% | 52.2% | **56.5%** ↑ | 52.2% | Mech 모두 ↑ |
| tri-slope (26) | 96.2% | **100%** | 38.5% | 42.3% | 50.0% | **53.8%** ↑ | Mech 모두 ↑ |
| gable (28) | 96.4% | **100%** | **64.3%** | 53.6% | 57.1% | 53.6% | Baseline 최고, 모든 Mech ↓ |
| flat (25) | 100% | **100%** | **56.0%** | 44.0% | 40.0% | 44.0% | Baseline 최고, 모든 Mech ↓ |

![fig7](figures/fig7_type_vs_condition.png)  
*Figure 7. Roof type × Condition (pre-fix). 점선 = GT direct, 파선 = convex 천장. Post-fix 로 갱신 필요.*

**v4 일관 패턴 (post-fix)**:
- **Complex/hip/tri-slope** (복잡 건물): Structure/Both 가 +10~17%p — v3 와 동일 결론, magnitude 유사
- **Flat/gable** (단순 건물): **모든 메커니즘이 Baseline 보다 낮음** — Mutual 만이 아니라 Structure 도. (v3 에서도 동일 방향이었으나 Mutual 의 −29%p 회귀가 dominant 했고 Structure 의 −8~−11%p 는 묻혔음. v4 에서 Mutual 회귀 −10~−12%p 로 축소되어 Structure 의 회귀가 비교 가능한 수준으로 보임)
  - Pre-fix: gable Mutual 25.0% (Baseline 대비 −28.6%p), flat Mutual 32.0% (−12.0%p)
  - Post-fix: gable Mutual 53.6% (Baseline 대비 −10.7%p), flat Mutual 44.0% (−12.0%p)
  - Structure: gable 57.1% (−7.2%p), flat 40.0% (−16.0%p) — flat 에서 오히려 Mutual 보다 더 회귀
- **GT convex 천장**: 단순 건물 (flat/gable/tri-slope) 100%. 즉 알고리즘은 완벽 처리 가능. 회귀 원인은 *Stage 2 primitive quality* + *Stage 3 clustering 변형* 의 부정적 상호작용 (D' 가설).

### 4.5 val3dity 에러 분포 (v4, post-fix)

| Condition | 203 (non-planar) | 204 (orient) | 104 (multi-comp) | v3 → v4 (203) |
|---|---|---|---|---|
| Baseline | 54 | 1 | 0 | 73 → 54 (−19) |
| Mutual | 52 | **4** ↑ | 0 | 81 → 52 (**−29**) |
| Structure | **46** ↓ | 0 | 1 | 64 → 46 (−18) |
| Both | 52 | 0 | 0 | 66 → 52 (−14) |

**v4 관찰**:
- 203 (non-planar) 여전히 dominant 이지만, Mutual 의 203 절대값이 **Baseline 과 비슷**해짐 (52 vs 54). Pre-fix 의 81 → 52 가 가장 큰 감소 — Mutual 에서 bbox 버그가 가장 심하게 발동했었음.
- **Structure 의 203 가 가장 적음** (46) — 메커니즘 2 가 Stage 3 출력 폐합에 도움이 되는 정량 증거. Pre-fix 와 동일 결론, magnitude 유사.
- Mutual 의 204 (orientation) 4 건 — Baseline 1 건 대비 ↑. Mutual 후 normal 정렬이 Stage 3 face orientation 일관성에 부정적 영향 가능성. 절대값 작지만 v4 신규 관찰.

![fig3](figures/fig3_error_heatmap.png)
*Figure 3. Pre-fix 기반. Post-fix 갱신 필요.*

---

## 5. 결과 해석

### 5.1 명확한 관찰 (5, v4)

1. **L_mutual 은 Stage 2 primitive 수준에서 의도대로 작동** (Wall vert 28→79%, σ_normal_intra −14%, corner 영역 균질화 D4) — 변화 없음
2. **L_structure 는 Stage 2 primitive 수준에서 효과 미미** (σ_normal_intra +1%, σ_coplanar 미세 개선 −2~−9%) — 변화 없음 (primitive level, bbox 무관)
3. **Stage 3 (val3dity) 에서는 Structure/Both 가 Baseline 대비 +1.5~2.3%p 개선** (v3: +3%p, magnitude 약간 축소). 203 에러 기준 Structure 가 여전히 최저 (46 vs Baseline 54).
4. **Mutual 단독은 Stage 3 val3dity 회귀** (−3.8%p, v3 의 −8.4%p 에서 절반으로 축소) — bbox 버그 효과 제거 후에도 회귀는 잔존. 단순 건물 (flat/gable) 에서 여전히 두드러짐.
5. **Type 별 패턴**: 복잡 건물 (complex/hip/tri-slope) 에선 메커니즘 효과 ↑, 단순 건물 (flat/gable) 에선 모든 메커니즘 ↓ — v4 신규: Mutual 뿐 아니라 *Structure 도 단순 건물에서 약간 회귀*.

### 5.2 미확정 — 가설 × 증거 매트릭스

| 미확정 | 가설 | 증거 (확인) | 증거 (반증) | 결론 |
|---|---|---|---|---|
| **Mutual 의 단순 건물 회귀 메커니즘** | A: Mutual 이 wall direction 손실 (D1) | bid=2: clusters 7→5, walls 4→2 | bid=22 baseline 도 fail, bid=21 Mutual pass | **건물별 다름 — D1 사례는 일반화 못함** |
| | B: 처마 등 수직 wall detail 손실 | — | GT walls 100% 수직 (D4 verified) | **틀림** |
| | C: photo loss 와 tug-of-war | — | r(mutual, photo) = -0.03 | **틀림** |
| | D (v3): Stage 3 convex hull + L_mutual primitive 부정적 상호작용 | pre-fix 203 증가 | **v4 post-fix: Mutual 203=52 (Baseline 54 와 유사), 회귀 magnitude −8.4 → −3.8%p** | **부분 부정** — 절반은 bbox 버그 |
| | **D' (v4 신규): 단순 건물에서 Stage 2 메커니즘이 *과조정***  | flat/gable GT convex 100%, 모든 메커니즘 ↓ (Mutual −12%p, Structure −16%p) | — | **그럴듯** — baseline primitive 도 단순 건물엔 충분, 추가 정렬이 polytope 안정성 손상 |
| | E (v4 신규): Mutual 후 face orientation (204) 증가 | post-fix Mutual 204=4 (Baseline 1) | 절대값 작음, 회귀 magnitude 와 부정합 | 부분적, 약함 |
| **L_structure 의 Phase 2 효과 부재** | A: 데이터 복잡도 | — | Phase 1 / 2 의 loss magnitude 비슷 | 약함 |
| | B: w_structure 작아서 | — | Phase 2 의 L_struct/L_photo ratio 가 Phase 1 의 20x | **틀림** |
| | **C: Grouping 알고리즘이 noisy 데이터에서 부정확** | D2: bid=21 (complex) 에서 σn 악화 (+3%) | bid=2 에선 σn 개선 (-13%) | **부분 맞음, 건물별 차이** |
| | **D: Per-primitive gradient 희석** (그룹당 prims 수 많음) | TB: loss/structure max 0.0003 | Phase 1 도 비슷한 magnitude | **불확실** |
| **Mutual + Structure synergy 부재** | A: 두 메커니즘이 같은 변수 (n_i) 에 작용, gradient 크기 차이 (Mutual peak 91 vs Structure 0.0003) | TB 측정 | — | **확실** |
| | B: Mutual 이 Structure 의 grouping input 변형 | D1: Mutual 후 cluster 수 변화 | Both 에서 Structure 가 일부 회복 | **확실** |
| | C: 학습 중 자동 조정 가능? | T iter 마다 재그룹핑 있음 | Structure 가 group split 능력 없음 (hard assignment) | **자동 조정 불가** |

→ **방법론적 시사점**: 메커니즘 1+2 의 "순환 효과" 가설은 **두 메커니즘이 같은 grouping 을 공유** 가정. 실제로는 Mutual 이 grouping 자체를 변형 → 가설 부분 부정.

### 5.3 정리된 인과 사슬 (v4)

```
L_mutual (Stage 2):
  Wall normal verticalization (28→79%) ✓ 의도대로
        ↓
  Stage 3 Step 2 clustering (cos > 0.85):
    수직화된 Wall normals 가 cos similarity 높아짐
        ↓
  단순 건물에서 polytope 안정성 약간 손상 (회귀 −3.8%p, post-fix)
  ※ pre-fix 의 −8.4%p 중 절반은 bbox 버그가 Mutual 에서 더 자주 발동했기 때문
        ↓
  Step 6 val3dity: 203 (Baseline 와 유사), 204 약간 증가 (1→4)

L_structure (Stage 2):
  Group 평면 정렬 효과 약함 (σ_normal_intra +1%)
  σ_coplanar 약간 개선 (-2~-9%)
        ↓
  Stage 3 Step 2 clustering: grouping 자체는 baseline 과 유사
        ↓  
  Step 3 대표평면: σ_coplanar 개선 → 평면 정합도 ↑
        ↓
  Step 4 polytope: plane intersection 더 깨끗
        ↓
  Step 6: 203 에러 감소 (54→46), val3dity +2.3%p

Both:
  Mutual + Structure 동시 — val3dity 54.2% (Structure 55.0% 보다 약간 낮음)
  Synergy 부재 확인 — Structure 단독 ≥ Both
  단순 건물에선 Both 도 회귀 (gable 53.6, flat 44.0; Baseline 64.3, 56.0)
```

**v4 핵심 update**: pre-fix 의 "Mutual → wall over-merge → 203 fail" 인과 사슬이 dominant 라고 봤는데 (D1: bid=2 의 4→2 walls), post-fix 데이터로 보면 **bbox 버그가 dominant 였음**. 잔존 회귀의 메커니즘은 D' (단순 건물 과조정) 가 더 그럴듯.

---

## 6. 한계 및 다음 단계

### 6.1 측정의 한계 (v4)

- **Sequential baseline 미측정**: MVS+RANSAC+convex 와 직접 비교 안 됨. Joint > Sequential 정량 증거 없음
- **val3dity 의 binary 특성**: 메커니즘의 partial improvement 가 잘 안 보임
- ~~Stage 3 (convex) 의 천장이 76.3%~~ → **v4: 실제 천장 96.2%**. 우리 best (Structure 55.0%) 와 천장 사이에 **+41%p 개선 여지**. 알고리즘 자체보다 *Stage 2→3 인터페이스* 가 진짜 병목 가능성 (별도 분석 필요)
- **bbox_margin 자동화 이전 측정값 (REPORT v3) 의 해석 신뢰도 저하**: 특히 4.5 의 203 에러 분포, 4.4 type 별 패턴, 5.3 인과 사슬 일부가 bbox 버그에 의해 왜곡됐었음. 본 v4 가 정정.

### 6.2 다음 단계 (재학습 없는 분석)

- 학습 중 gradient norm 측정 (L_mutual vs L_structure 의 per-primitive gradient 비교) — D2 미확정 가설 D 검증
- 더 많은 building 의 D3 분석 (현재 4 건물) — 통계적 일반화
- 6-step 별 성공/실패 비율 집계 (현재는 사례 단위)

### 6.3 다음 단계 (재학습 필요)

- **Clustering 알고리즘 robustness 개선** (cos threshold 더 엄격 / wall azimuth 명시 / min_group_size 완화) → 같은 ckpt 로 재실행 가능
- **L_structure 의 group split 능력**: 현재는 grouping 후 그룹 내 정렬만. Split 도 가능하게 (contrastive loss 도입) → 재학습
- **L_mutual 의 quadratic 페널티** (linear → 제곱) → 재학습

### 6.4 Stage 3 알고리즘 교체 (천장 상승) — v4 우선순위 하향

v3 에선 "convex 천장 76.3% 가 한계" 라서 PolyFit/City3D 등 알고리즘 교체가 우선이었음. **v4: 천장 96.2% 라 알고리즘 자체 한계는 거의 없음**. 우선순위 재조정:

- ~~PolyFit 완성~~ → 우선순위 ↓ (천장 추가 상승 여지 작음)
- **Stage 2→3 인터페이스 정렬 (Stage 2 group_id 를 Stage 3 입력으로 직접 전달)** → 우선순위 ↑ (현재 41%p 격차의 주된 원인 가능성)
- **L_normal_align 의 Phase 2 약효 진단** (C3, photo loss redundancy 가설) → 우선순위 ↑

**Stage 3 알고리즘 교체는 41%p 격차를 인터페이스 정렬로 줄인 후 잔존 격차에 대해 재평가.**

---

## 7. PolyFit 시도 (참고)

| 단계 | 상태 |
|---|---|
| CGAL 5.6 + GLPK 빌드 | ✓ |
| GLPK MIP | 16+ plane 건물 timeout |
| SCIP 10.0 + 재빌드 | ✓ |
| MIP 솔빙 | <10s/건물 |
| Surface_mesh 생성 | ✓ |
| **val3dity compliance** | ✗ (303 non-manifold, 307 wrong orientation) |

핵심 미해결: CGAL Surface_mesh 가 face 별 독립 vertex 로 출력 → stitch_borders 가 float-precision 한계로 close 못함. Python BFS orientation propagation 또는 polygon_soup 접근 필요 (1-2h).

![fig8](figures/fig_polyfit_steps_large.png)  
*Figure 8. PolyFit step-by-step (GT input). Step 3 mesh 는 watertight 안 닫힘.*

---

## 8. 결론 (v4)

**확정된 기여**:
1. L_mutual 이 Phase 1 의 Wall 수직화 효과를 Phase 2 에 부분 전이 (28→79%)
2. L_structure 가 복잡 건물 (complex/hip/tri-slope) 에서 Stage 3 val3dity 의미있게 개선 (+10~17%p, post-fix 에서도 유효)
3. 메커니즘별 다른 metric 축 (Mutual: face IoU 0.214→0.240; Structure: val3dity, SemAcc)
4. ~~Stage 3 algorithm + Stage 2 mechanism 부정적 상호작용~~ → **v4: 부정적 상호작용은 일부만 잔존** (회귀 magnitude 절반은 bbox 버그)
5. **v4 신규: 단순 건물 (flat/gable) 에서는 모든 메커니즘이 Baseline 보다 낮음** — "단순 입력엔 추가 정렬이 과조정" 가설 성립

**한계**:
- L_structure 의 Phase 2 매커니즘 약함 (σ_normal_intra +1%) — Phase 1 −45% 대비 큰 차이, 원인 미확정 (C3)
- "순환 효과" 시너지 미입증 — Both ≤ Structure (val3dity)
- Sequential baseline 미측정 — joint 우세 정량화 불가
- **v3→v4 revision 자체가 시사**: Stage 3 측정 인프라의 신뢰성 점검 필요. bbox 같은 1줄 수정이 conclusion 을 뒤집을 수 있다는 fragility.

**개선이 필요한 곳** (v4 우선순위):
1. **Stage 2→3 인터페이스 정렬** (group_id 전달) — 41%p 격차의 주 원인 가능성
2. **C3 진단** — L_normal_align 의 Phase 2 약효, photo loss redundancy 가설 검증 (1 시간)
3. ~~Clustering 알고리즘 robustness~~ — bbox fix + 인터페이스 정렬로 상당 부분 해결 예상

---

## 9. 부록 — 파일 위치

```
results/phase2_ablation_citygml/
├── REPORT.md                       # 본 문서 (v4)
├── stage2_primitive_metrics.json   # §3.2 데이터
├── _gt_direct/summary.json         # GT direct 93.9%
├── _gt_stage3_test/summary.json    # [v3, pre-fix] GT convex 76.3% — obsolete, bbox 버그
├── _gt_stage3_convex_fixed/summary.json  # [v4, post-fix] GT convex 96.2% ★
├── _gt_stage3_test_2_5d_v2/summary.json  # GT 2.5D 67.2% (별도 알고리즘)
├── _gt_polyfit_test/summary.json   # PolyFit 미완
├── _diag/d1/comparison_bid{2,22}.json    # D1 raw data
├── _diag/d2/d2_results.json        # D2 grouping 비교
├── _diag/d3/                       # D3 raw
├── _diag/d4_stats.json             # D4 wall tilt 통계
├── {baseline,mutual,structure,both}/
│   ├── eval/eval_summary.json      # [v3, pre-fix] §4.3 v3 데이터 — obsolete
│   ├── eval_fixed/eval_summary.json # [v4, post-fix] §4.3 v4 데이터 ★
│   ├── stage3/stage3_summary.json  # [v3, pre-fix] obsolete
│   └── stage3_fixed/stage3_summary.json # [v4, post-fix] §4.4 type 별 데이터 ★
└── figures/
    ├── fig1_citygml_4cond.png
    ├── fig2_val3dity_bars.png      # §4.3
    ├── fig3_error_heatmap.png      # §4.5
    ├── fig4_syntheticA_mapping.png
    ├── fig5_representative_building.png
    ├── fig6_success_failure_cases.png
    ├── fig7_type_vs_condition.png  # §4.4
    ├── fig8 = fig_polyfit_steps_large.png  # §7
    ├── fig_d1_bid002.png           # §4.1
    ├── fig_d1_bid022.png
    ├── fig_d2_structure_grouping.png  # §3.2
    ├── fig_d3_bid{2,22,6,21}_steps.png  # §4.1, §4.2
    └── fig_d4_baseline_wall_tilt.png  # §3.3

scripts/phase2_synthesis/
├── diag_d1_mutual_regression.py    # D1
├── diag_d2_structure_grouping.py   # D2
├── diag_d3_stage3_breakdown.py     # D3
└── diag_d4_baseline_wall_tilt.py   # D4
```
