# Stage 3 (primitives → CityGML) 방향 — Claude Web 브리핑 v3

> 이 문서는 새로운 Claude 대화에 그대로 붙여넣어 처음부터 맥락을 잡고 기술 논의를 이어가기 위한 자료입니다. v3 는 v2 이후의 *GT_convex 측정 오류 발견* 까지 반영.

## 0. v2 이후 변경 — 한 줄

v2 까지는 "Stage 3 알고리즘 천장 96.2% 라 알고리즘 자체 한계는 작음 → Track 1 (인터페이스 정렬) 우선" 이었는데, **GT_convex 가 사실 GT 의 절반 높이로 systematic 축소된 잘못된 reference 였음** 을 발견. 진짜 천장은 미정 상태이며, 그럼에도 Track 1 우선 결론은 유지 (이유는 §6).

---

## 1. 연구 배경 (압축)

박사 연구: **도시 규모 건물의 구조적 3D 복원 — 기하-의미론 공동 최적화**

- Base: 미분 가능 렌더링 (gsplat + 2DGS)
- 두 메커니즘:
  - **L_mutual** (메커니즘 1, intra-primitive): wall=수직, terrain=수평 도메인 규칙. p_c × 기하오차 → n_i, f_i 양방향 gradient
  - **L_structure** (메커니즘 2, inter-primitive): 매 T iter 그룹핑 → 그룹 내 normal/center 정렬. n_i, c_i 만 작용
- Pipeline: Stage 1 (SfM/MVS+seg+gravity) → Stage 2 (joint opt) → **Stage 3 (CityGML 변환)** ← 현재 문제 지점

검증 단계:
- Phase 1 (MatrixCity): primitive 수준 검증, **6/6 통과**
- Phase 2 (3D BAG 합성): CityGML 평가, **진행 중**, 측정 인프라 문제 두 건
- Phase 3 (real UAV): 미착수

---

## 2. 현재 데이터 (Phase 2, post-bbox-fix)

### Stage 2 — primitive 수준

| 지표 | 정의 | 방향 | Baseline | Mutual | Structure | Both |
|---|---|---|---|---|---|---|
| eval PSNR | rendering | ↑ | 40.35 | 40.93 | 40.96 | 39.81 |
| Wall vert-frac | wall 중 \|n·g\|<0.15 | ↑ | 28.0% | **79.3%** | 28.4% | **79.4%** |
| σ_normal_intra (deg) | 그룹 내 분산 | ↓ | 14.74 | 12.63 | **14.88** | 12.99 |
| σ_coplanar (m) | 그룹 내 평면 정합 | ↓ | 1.91 | 1.84 | **1.86** | 2.01 |

**Phase 1 → Phase 2 차이**:
- Wall vert: 17→88% (Phase 1) → 28→79% (Phase 2). 부분 전이.
- σ_normal_intra: −45% (Phase 1 Structure) → **+1%** (Phase 2 Structure). **거의 사라짐 — C3 모순.**

### Stage 3 — CityGML 출력 (post-fix)

| Cond | val3dity | face IoU | Hausdorff | Sem acc | σ_normal 3D |
|---|---|---|---|---|---|
| Baseline | 52.7% | 0.214 | 11.37 | 21.6% | 9.09° |
| Mutual | 48.9% ↓ | **0.240** | 11.54 | 20.6% | **8.73**° |
| Structure | **55.0%** | 0.221 | 11.45 | **22.0%** | 9.18° |
| Both | 54.2% | 0.227 | 11.56 | 20.4% | 9.00° |

조건 ranking (val3dity): **Structure > Both > Baseline > Mutual**

Type 별 패턴:
- **복잡 건물 (complex/hip/tri-slope)**: Structure/Both 가 +10~17%p
- **단순 건물 (flat/gable)**: 모든 메커니즘이 Baseline 보다 낮음 (Mutual −10~12%p, Structure −7~16%p)

---

## 3. 발견된 모순 4 가지

### C1: Mutual 의 Stage 3 회귀

**관찰**: val3dity 에서 Baseline 52.7% vs Mutual 48.9% (−3.8%p)
**Pre-fix 에선 magnitude 가 −8.4%p 였는데 bbox 버그 정정 후 절반 축소 → 잔존 −3.8%p 의 메커니즘은 미확정.**

가설 후보:
- D' (단순 건물 과조정): flat/gable 의 GT convex 천장 100%, 즉 baseline primitive 도 수직, Mutual 의 추가 정렬이 polytope 안정성 손상
- E: Mutual 후 face orientation (val3dity 204) 약간 증가 (1→4)

### C2: Stage 2 ↔ Stage 3 인터페이스 단절

```
Stage 2 (src/stage2/grouping.py:35):
  키 = (class, voxel_3d (size 0.05), normal_dir_quantized (12 bins))
  매 T iter 그룹 ID 부여 + rep_n, rep_d 계산
  L_structure 가 학습 내내 사용

Stage 3 (src/stage3/clustering.py:12):
  완전히 다른 알고리즘: hierarchical clustering (cos > 0.92) + spatial split
  Stage 2 의 group_id 를 받지 않음
```

→ L_structure 가 학습 내내 만든 group 정보 (group_id, rep_n, rep_d) 가 **Stage 3 에 전달되지 않고 통째로 버려지고 재계산됨**. 메커니즘 2 의 효과가 Stage 3 측정에서 부분적으로만 드러나는 *구조적* 원인.

### C3: L_normal_align 의 Phase 2 약효 (미검증)

L_structure 는 두 component:
- L_normal_align: $\sum (1 - n_i \cdot n_k)^2$ → σ_normal_intra 타깃
- L_coplanar: $\sum (n_k \cdot c_i + d_k)^2$ → σ_coplanar 타깃

Phase 1 vs Phase 2:
- σ_normal_intra: −45% → +1% (**L_normal_align 거의 작동 안함**)
- σ_coplanar: −16% → −2~−9% (L_coplanar 약하나마 작동)

**가설 (미검증)**: PSNR 40+ 의 강한 photometric supervision 이 normal 을 이미 정렬해 L_normal_align 이 redundant. 학습 trajectory 상 normal 이 일찍 saturate.

검증 방법: Structure ckpt 의 학습 마지막 50 iter σ_normal_intra trajectory dump (1 시간).

### Bug 1: bbox_margin 자동화 오류 (정정 완료)

`src/stage3/plane_intersection.py` 의 bbox_margin 이 고정 1.0m → flat 건물에서 QHull "Initial simplex flat" → 14 건물 처리 실패. `max(5.0, 0.5×extent)` 로 자동화 후:

| Cond | v3 (pre-fix) | v4 (post-fix) | Δ |
|---|---|---|---|
| Baseline | 40.5% | 52.7% | +12.2%p |
| Mutual | 32.1% | 48.9% | **+16.8%p** |
| Structure | 43.5% | 55.0% | +11.5%p |
| Both | 43.5% | 54.2% | +10.7%p |

→ C1 magnitude 절반이 bbox 버그 영향이었음.

### Bug 2: GT_convex systematic 축소 (정정 미완)

`gt_stage3_test.py` 에서 GT face 를 primitive 로 입력 후 같은 convex polytope 알고리즘 통과 → "Stage 3 algorithm 천장" 으로 측정 (v4 에서 96.2%).

**검증 결과 (131 건물 전수)**:
- 평균/중앙값 비율 (convex_height / GT_height): 0.55-0.57
- 88% 건물 (115/131) 에서 *절반 이하 높이*
- 극단: bid 3 (complex) 25.78m → 3.10m (12%)

**시사점**: v4 의 "천장 96.2%" 는 *GT 가 절반으로 줄어든 polytope 의 통과율* 이지 *알고리즘 천장* 이 아님. 진짜 천장 미정.

직접 검증 (building 1):
- GT mesh 원본: 16.61m
- 우리 Stage 3 출력: 16.41m ← GT 와 거의 일치
- GT_convex (잘못된 reference): 8.56m

**즉 우리 Stage 3 출력 자체는 GT 와 비슷한 크기를 만듦** — 문제는 비교 reference. 시각 인상 (web viewer) 과도 부합.

---

## 4. 시도된 Stage 3 접근 (모두 답 안나옴)

- Convex polytope (현재 baseline)
- 2.5D hybrid (구현 버그)
- PolyFit (CGAL+SCIP, watertight 후처리 미완)
- Building instance 분리 우선 (Codex 추천, 효과 없음)
- Wall barrier/separator graph 등 (모두 dead exploration, 정리됨)

공통 잘못된 전제: "**Stage 3 는 raw primitive 를 받아 알아서 처리한다**". 실제로는 Stage 2 가 이미 grouping 이라는 절반의 작업을 했는데 그걸 export 안 하고 있었음 (C2).

---

## 5. Eval metric 의 가혹성 (Step 2 발견)

GT_convex 가 잘못된 reference 였음에도, *상대 비교* 에서 metric 자체의 가혹성도 알게 됨:

| Metric | vs scene.obj GT (~22 face/bldg) | vs GT_convex (~7 face/bldg) |
|---|---|---|
| sem accuracy | 21.6% | **46.1%** |
| face IoU | 0.214 | **0.154** ↓ |
| val3dity | 52.7% (binary) | 동일 |

**해석**:
- Sem acc 21% → 46%: Greedy 1-to-1 matching 으로 face count mismatch 시 GT face 64% 가 unmatched (pred=BG) 행 → sem 엄청 깎임. 진짜 sem quality 는 46% 정도.
- face IoU 오히려 ↓: pred 7 면이 GT 22 면 중 *cherry-pick* 했을 때 IoU 0.21, 22 → 7 로 줄여 cherry-pick 불가하면 0.15. **즉 0.21 도 inflated 였음, 진짜 face 정합도는 더 낮음.**

단 GT_convex 자체가 GT 의 절반이라 이 비교의 *절대 의미는 흐려짐*. 진짜 metric 평가는 **Step 1 (인터페이스 정렬) + 진짜 천장 재측정 후** 가능.

---

## 6. 제안 방향

### Track 1 (메인): Stage 2→3 인터페이스 정렬

```
1. src/stage2/train.py 마지막에 group_primitives() 호출
2. ckpt 에 group_id, rep_n, rep_d export
3. src/stage3/clustering.py 삭제 또는 thin wrapper
4. Stage 3 = 4 단계: group → 대표평면 → 평면 교차 → polygon
5. 4 조건 재측정 → CityGML → val3dity
```

기대 효과:
- C2 해소 (정의-동작 일치)
- C1 잔존 회귀 추가 해소 (Stage 2 grouping 이 voxel hash 라 공간 분리 보장 → over-merge 구조적 발생 불가)
- 단 C3 는 별도 (Stage 2 자체 문제)

작업량: 4-6 시간

**왜 GT_convex 발견 후에도 Track 1 우선이 유지되는가**:
- GT direct 93.9% (topology 보존) 가 알고리즘 천장의 *lower bound* — 우리 best 55% 대비 +39%p 격차 존재
- 이 격차의 상당 부분이 인터페이스 단절 (C2) 에서 발생할 가능성
- Stage 3 알고리즘 자체 (convex polytope) 는 building 1 직접 검증으로 *GT 비슷한 출력 만듦* 확인 → 알고리즘 교체보다 인터페이스 수정이 우선

### Track 2 (병행, 1 시간): C3 진단

L_normal_align redundancy 가설 검증:
- Structure ckpt 학습 마지막 50 iter σ_normal_intra trajectory dump
- 빠르게 saturate → photo loss 가설 지지 → thesis 부정 X
- 끝까지 안 줄어듦 → 다른 원인

### Track 3 (1-2 시간): 진짜 천장 재측정

GT_convex 가 왜 절반인지 디버그 + 정정:
- `process_building(cos_thresh=1.0)` 으로 GT 다시 polytope 화 (face 합치기 비활성화)
- 또는 GT direct 93.9% 채택

진짜 천장이 정해지면 v5 REPORT 갱신 + 우리 best 의 천장 대비 위치 확정.

---

## 7. 정합성 평가

| 기준 | 평가 |
|---|---|
| **연구 의도 정합성** | ✓ thesis main claim 보존, 측정 인터페이스만 정렬 |
| **논리적 일관성** | ✓ Phase 1 (primitive 수준) ↔ Phase 2 (Stage 3 출력 수준) 평가 체계 통일 |
| **모순 해소** | C1 잔존 + C2 해소 (Track 1). C3 별도 진단 (Track 2). 천장 재측정 (Track 3) |

남는 위험: 정직한 측정 후에도 메커니즘 효과가 약하면 thesis 와 결과 모순 → 데이터의 진실로 받아들이고 thesis 재정의 (예: "메커니즘은 primitive 수준에서 작동, 강한 supervision 환경에서는 Stage 3 변환에서 부분적 정보 손실").

---

## 8. v1 → v2 → v3 변화 요약

| 항목 | v1 (pre-bbox-fix) | v2 (post-bbox-fix) | v3 (post-GT_convex 발견) |
|---|---|---|---|
| Stage 3 천장 | 76.3% | 96.2% (algorithm 거의 한계 없음) | **미정** (GT_convex 자체가 잘못됨) |
| 우리 best | 43.5% (천장의 57%) | 55.0% (천장의 57%) | 55.0% (천장 대비 위치 미정, GT direct 93.9% 대비 −39%p) |
| Mutual 회귀 | −8.4%p | −3.8%p | −3.8%p |
| C1 dominant 원인 | Stage 3 clustering over-merge | bbox 버그 50% + 잔존 D' 가설 | (변경 없음) |
| Stage 3 알고리즘 교체 우선순위 | 높음 | 낮음 | **여전히 낮음** (building 1 직접 검증) |
| 인터페이스 정렬 우선순위 | 중간 | 높음 | **여전히 높음** |
| Stage 3 출력의 *진짜 quality* | 측정 안 됨 | metric 부풀려진 측정만 | **시각적으로 GT 와 비슷, metric 으론 낮음 — 둘 다 일부 진실** |

---

## 9. 논의하고 싶은 것

1. **Track 1 인터페이스 정렬이 v3 (천장 미정 상태) 에서도 첫 우선순위가 맞는가?**
2. **D' 가설 (단순 건물 과조정)** 이 합리적인가? 메커니즘 설계에 building complexity 반영 필요할까?
3. **C3 의 photo loss redundancy 가설**: Phase 1 (PSNR 22) → Phase 2 (PSNR 40+) supervision 강도 차이가 메커니즘 2 효과를 dominantly 결정한다면, real UAV (PSNR ~25-30 예상) 에서는 어떻게 작동할까?
4. **Measurement infrastructure fragility**: bbox 1 줄 + GT_convex 두 차례 측정 오류로 conclusion 흔들렸음. *이 자체가 박사논문 contribution* (reproducibility 단원) 의 일부가 될 수 있는가?
5. **시각 vs metric 격차**: 우리 Stage 3 출력이 GT 와 시각적으로 비슷한데 face IoU 0.16. 이걸 어떻게 보고할까? Metric 재설계 vs 시각 평가 강화?
6. 인터페이스 수정 후에도 4 조건 차이가 미미할 경우 thesis 재정의 방향 — "메커니즘은 primitive 수준에서 작동, supervision 강도가 dominant" 같은 conditional claim 이 받아들일 만한가?

---

## 10. 첫 행동 (실행 가능한 단계)

만약 Claude 가 작업한다면 추천 순서:

```
[1] (가장 가벼움, 1h) Track 2: C3 진단
    - Structure ckpt 의 σ_normal_intra trajectory 측정
    - Photo loss redundancy 가설 검증
    
[2] (1-2h) Track 3: 진짜 천장 재측정
    - cos_thresh sweep 또는 GT direct 채택
    - v5 REPORT 갱신
    
[3] (4-6h) Track 1: 인터페이스 정렬 (메인)
    - 위 두 결과 위에서 본격 수정
```

각 단계마다 결과 확인 → 다음 단계 결정. 1-2 일 안에 Phase 2 결론 가능.

---

## 11. 주요 파일 위치

```
src/stage2/
├── grouping.py       # voxel hash grouping (학습용)
├── loss/mutual.py    # L_mutual
├── loss/structure.py # L_structure
└── train.py          # 학습 entry

src/stage3/
├── clustering.py        # hierarchical clustering (←C2 의 핵심, Track 1 에서 수정)
├── plane_intersection.py # convex polytope (bbox_margin fix 들어있음)
└── citygml_export.py    # CityJSON export

scripts/phase2_synthesis/
├── eval_citygml.py        # eval metric (face IoU, sem acc, val3dity)
├── gt_stage3_test.py      # GT 를 Stage 3 통과시켜 천장 측정 (← GT_convex 오류 출처)
└── obj_gt.py              # scene.obj parser

results/phase2_ablation_citygml/
├── REPORT.md                  # 상세 진단 (v4)
├── _gt_stage3_convex_fixed/   # GT convex polytope 결과 (잘못된 reference)
├── {baseline,mutual,structure,both}/
│   ├── eval_fixed/eval_summary.json    # post-fix metric
│   └── stage3_fixed/                   # post-fix CityJSON outputs
```

---

이 정도면 새로운 대화에서 같은 깊이로 논의 이어갈 수 있을 것입니다. 모르는 부분이 있으면 위 §11 의 파일들을 reference 로 들어 질문해주세요.
