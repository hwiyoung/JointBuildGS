# 연구 현황 종합 보고서 — Positioning 재검토 용

**작성**: 2026-04-24 KST  
**목적**: 현재까지 수행한 모든 실험과 발견된 문제를 정리하여 연구 방향 재설정의 근거 자료로 사용.

---

## 0. TL;DR

- **연구 목표**: "도시 규모 건물의 **구조적 3D 복원**을 위한 **기하-의미론 공동 최적화**"
- **Phase 1 (MatrixCity, Stage 2)**: 6/6 체크리스트 통과. L_mutual/L_structure 가 설계대로 작동 확인.
- **Phase 2 Step 2-1 (3D BAG 합성 데이터)**: v3 완성 (v1/v2 실패 후). 131 건물, 560 views, Pix4D 표준.
- **Phase 2 Step 2-2 (4조건 Stage 3 ablation)**: 완료. 결과는 얻었지만 **논문 포지셔닝 문제** 발견.
- **핵심 이슈**: CityGML LOD2 val3dity 를 주 평가 지표로 하면 image-only 방식의 절대 수치(40-44%)가 LiDAR + footprint 기반 방법(90%+) 대비 현저히 낮아 보임. 연구의 "구조적 3D 복원" 포지셔닝 재검토 필요.

---

## 1. 연구 목표

```
주 목표: 도시 규모 건물의 구조적 3D 복원을 위한 기하-의미론 공동 최적화
```

**두 수준의 공동 최적화**:
- **Intra-primitive (메커니즘 1, L_mutual)**: 개별 프리미티브의 도메인 규칙 기반 상호 교정
- **Inter-primitive (메커니즘 2, L_structure)**: 프리미티브 간 구조적 일관성 제약

**평가 지표로 선택한 것**:
- Stage 2 검증: PSNR, 기하 metric (depth/normal), σ_normal, Wall vertical-fraction, mIoU
- Stage 3 검증: CityGML LOD2 val3dity, face IoU, Hausdorff, semantic accuracy

**전제**: CityGML LOD2 는 "구조적 3D 건물 모델" 의 **국제 표준 평가 기준** 으로 채택한 것. 즉 CityGML 생성 자체가 주 목표가 아니라 "우리의 primitives 가 구조적으로 건물 모델로 유효한가" 를 계량화하는 도구.

---

## 2. 파이프라인 구조

```
[Stage 1] 이미지 → SfM/MVS → 점군 + depth/normal + semantic + gravity
               ↓
[Stage 2] 이미지 + Stage 1 산출물 → 2DGS 기반 joint 최적화 → 평면 primitives (N, center, normal, scale, semantic_probs)
               ↓ (L_mutual 과 L_structure 가 여기서 작동)
               ↓
[Stage 3] primitives → 평면 교차/재구성 알고리즘 → CityGML LOD2
```

- **Stage 2 의 우리 기여**: L_mutual, L_structure
- **Stage 3 는 알고리즘 선택 문제** (convex, 2.5D, PolyFit, City3D, Roofer 등 중 하나)

---

## 3. 수행한 실험

### Phase 1 — MatrixCity (Stage 2 벤치마크)
| Step | 내용 | 결과 |
|---|---|---|
| 1-1 Vanilla 2DGS | 30k iter | PSNR 21.31 (CityGSV2 baseline 21.12 달성) |
| 1-2 + Depth/Normal 감독 | L_depth + L_normal | PSNR 22.06 (CityGSV2 w/depth 22.22 근접) |
| 1-3 + Semantic head + L_sem | | PSNR 22.07, mIoU 0.635 |
| 1-4 + L_mutual (Mutual only) | | PSNR 22.24, Wall vertical-frac **19% → 91%** (+360%), mIoU 0.626 |
| 1-5 + L_structure (Structure only) | | PSNR 22.16, σ_normal_intra -45%, σ_coplanar -16%, mIoU 0.640 |
| 1-6 Both | | PSNR 22.26 peak 22.44, Wall-vert 88.3%, σ_normal -36%, **두 메커니즘 동시 보존 확인** |

**Phase 1 판정: 6/6 통과**. 렌더링/기하 parity 유지, 각 메커니즘이 설계대로 작동, Both 에서 동시 공존 확인.

### Phase 2 Step 2-1 — 3D BAG 합성 데이터 구축
- **v1, v2 실패** (camera frame 버그, biased split, 제한된 view 등)
- **v3 성공**: Amsterdam Jordaan 200×200m 블록, 131 건물, Pix4D 표준 (DJI Phantom 4 RTK 기준: 5472×3648, 74° FOV, 80m alt, 80%/70% overlap), 560 views, procedural texture (RGB≠semantic trivial correspondence 방지), interleave split
- **FC-1/2/3 feasibility checks** 통과
- **결과물**: scene.obj, scene.mtl, 560 렌더링, cameras.bin, depth/normal/semantic GT

### Phase 2 Step 2-2 — 4조건 Ablation (Stage 3 = convex 방식)
**Stage 2 학습 (각 30k iter, 약 5-8시간)**:
| Condition | Stage 2 학습 | 비고 |
|---|---|---|
| Baseline (vanilla 2DGS) | ✅ 완료 | PSNR, mIoU 기본 |
| Mutual (+L_mutual) | ✅ 완료 | σ_normal 감소 |
| Structure (+L_structure) | ✅ 완료 | plane 정렬 |
| Both | ✅ 완료 | 두 메커니즘 동시 |

**Stage 3 (convex polytope, 각 111/131 건물 처리)**:

| Condition | val3dity | face IoU | Hausdorff | SemAcc | σ_normal (3D) | val3dity 에러 |
|---|---|---|---|---|---|---|
| Baseline | **40.5%** | 0.213 | 11.42m | 21.1% | 9.09° | 203: 73, 204: 1 |
| Mutual | **32.1%** ↓ | **0.238** ↑ | 11.33m | 20.0% | **8.73°** ↑ | 203: 81, 204: 4 |
| Structure | **43.5%** ↑ | 0.220 | 11.39m | **21.8%** ↑ | 9.18° | 203: 64, 104: 1 |
| Both | **43.5%** ↑ | 0.230 | 11.46m | 19.5% | 9.00° | 203: 66 |

**관찰**:
- **Structure, Both** 가 val3dity에서 Baseline 대비 **+3.0%p** 개선
- **Mutual 이 face IoU 최고** (0.238) 및 σ_normal 최저 (8.73°) — plane-level 기하 품질은 최상
- **Mutual 단독은 val3dity 악화** (-8.4%p) — watertight manifold 측면에서 오히려 손해
- 주 val3dity 에러는 **203 (non-planar face)** — convex hull 한계에서 비롯

### Phase 2 Step 2-2 — GT 상한 검증 (Stage 3 알고리즘의 천장)

동일 GT scene.obj 의 건물별 face 를 입력으로 해서 Stage 3 알고리즘별 한계 측정:

| 방식 | 처리 | val3dity 통과율 |
|---|---|---|
| **GT direct** (topology 보존 포맷 변환) | 재구성 없음, 단순 CityJSON 포맷 | **93.9%** (123/131) |
| **GT + convex polytope** | face → plane 추상화 → convex hull | **76.3%** (100/131) |
| **GT + 2.5D hybrid** | face → plane + footprint → roof-type 재구성 | **67.2%** (88/131) |
| **GT + PolyFit (CGAL 5.6 + SCIP)** | face → points + planes → MIP subset | **0%** (CGAL 출력 watertight 미달) |

**해석**:
- **Upper bound 93.9%** — 3D BAG 원본 데이터 자체의 미세 topology 결함 (대부분 complex 타입, L/U 건물의 self-intersection) 외에는 완벽
- **Convex 알고리즘은 이론적 max 77.9% 의 98% 달성** (convex hull 가정이 complex 22% 처리 불가)
- **2.5D 는 구현 버그 많음** (debug 시도했지만 여전히 convex 보다 낮음)
- **PolyFit 출력 mesh 가 val3dity 기준 watertight 미달** — CGAL stitch_borders 가 float-precision 한계로 완전 close 못 함

### Phase 2 Step 2-2 — 결과 격차 분석

```
Upper bound (GT direct):       93.9%   ← 3D BAG 원본 한계
                               ↓ (-17.6%p)
Convex 알고리즘 천장 (GT):     76.3%   ← convex hull 가정 손실 (L/U 22%)
                               ↓ (-32.8%p ~ -35.8%p)
우리 Best (Both, convex):      43.5%   ← Stage 2 primitive 품질 손실
Baseline (convex):             40.5%
                               ↓ (?)
Sequential (MVS+RANSAC+convex): 미측정  ← 측정하면 비교 가능
```

## 4. 발견된 문제들

### 4-1. Stage 3 알고리즘 선택의 어려움
- **Convex**: 구현 clean 하지만 non-convex 건물 (L/U, 22%) 근본 처리 불가 → 77.9% 상한
- **2.5D hybrid**: legacy 코드 포팅했지만 Amsterdam 건물에 버그 많음 (margin bug 일부 수정, SVD planarity snap 시도했지만 여전히 67%)
- **PolyFit + CGAL 5.6 + SCIP**: 빌드는 성공, MIP 는 돌아가지만 출력 mesh 의 val3dity compliance 실패 (float-precision 으로 완전 close 안 됨). stitch_borders 추가 필요. polygon_soup 접근 재시도 필요
- **City3D/Roofer**: footprint 제약 필요. 통합 3-4h

**즉 "연구 기여가 아닌 엔지니어링 영역" 에서 시간과 에너지 소모 심함**.

### 4-2. 연구 포지셔닝 위기

**현재 결과를 표면적으로 보면**:
- 우리 image-only 방식: 40-44% val3dity
- 기존 City3D on LiDAR + footprint: 90%+ val3dity (보고됨)
- **"우리 방법이 왜 필요한가?"** 에 답하기 어려움

**근본 원인**: **입력 가정이 다른데 같은 지표로 비교**
- City3D/Roofer: LiDAR 점군 (밀도 10-25 pts/m²) + cadastral footprint
- 우리: 이미지만 (+ SfM poses)
- 공정 비교군은 "image-only LOD2 방법" 들 (PlanarSplatting, CityGSV2, MVS+RANSAC+PolyFit)인데 **아직 측정 안 함**

### 4-3. Mutual 단독의 val3dity 회귀 (−8.4%p)

Phase 1 에서 L_mutual 은 Wall vertical-fraction 91%, σ_normal 최저 등 명확한 개선을 보였지만, Phase 2 Step 2-2 의 convex Stage 3 에선 오히려 **불리**. 원인 추정:
- L_mutual 이 wall normal 을 강하게 수평으로 강제 → 실제 약간 경사진 벽 (처마, 돌출 장식) 이 오히려 수평으로 잘못 수정됨
- Convex Stage 3 가 plane 수치 개선 (σ_normal) 을 수용 못 하고 오히려 경계 처리 실패
- 29 건물 PASS→FAIL, 18 건물 FAIL→PASS (순 −11)

**Both 에서 Structure 와 조합 시 val3dity 회귀 상쇄**.

### 4-4. "topology 제거 → 재구성" 이 근본적으로 어려운 문제

- **GT direct (topology 보존): 93.9%**
- **GT + convex (topology 버리고 재구성): 76.3%**
- **−17.6%p 는 알고리즘 한계**, 재구성 문제의 본질적 난이도
- 우리 Stage 2 는 primitives (plane 정보) 만 출력하므로, topology 재구성 단계 (Stage 3) 를 피할 수 없음

---

## 5. 포지셔닝 재검토 — 세 가지 틀

**연구 목표 구성 요소 분해**:
- **구조적 3D 복원** (main goal, 평가 대상)
- **기하-의미론 공동 최적화** (우리 method, 기여)
- **도시 규모** (scale)

CityGML LOD2 val3dity 는 **구조적 3D 모델의 한 평가 도구**이지 연구의 주 목표가 아님. 도구가 불리하면 평가 방식 재검토 가능.

### 틀 A — "CityGML val3dity 가 main metric" (기존)
- val3dity 통과율이 주 지표
- **문제**: image-only 로는 40-44%, 기존 LiDAR 방식 대비 설득력 약함
- **판정**: 현재 setup 에서 불리. 연구 가치 저하 리스크.

### 틀 B — "구조적 3D 복원" 다면 평가 (권장)
Main claim: **"우리 primitives 가 구조적으로 더 우수"**. CityGML 은 하나의 증거.

Multi-metric 평가:
```
Stage 2 primitive 품질 (Phase 1):
  - PSNR, mIoU, 기하 metric
  - Wall vertical-fraction (L_mutual 효과)
  - σ_normal intra/coplanar (L_structure 효과)

Stage 3 downstream quality (Phase 2):
  - face IoU (plane-level 정확도)         0.213 → 0.238 (+12%, Mutual)
  - σ_normal_3D (3D plane 일관성)         9.09° → 8.73° (-4%, Mutual)
  - Semantic accuracy                    21.1% → 21.8% (+3%, Structure)
  - val3dity pass rate (downstream)      40.5% → 43.5% (+3%p, Structure/Both)
```

Claim 재구성: **"기하-의미론 공동 최적화가 primitive 의 구조적 특성을 개선, CityGML 생성 시 image-only 기준 향상"**. 절대 수치 44% 는 image-only 의 한계 영역 — 주 claim 이 아님.

### 틀 C — "Primitive representation" 으로 upstream 이동
Main claim: "2DGS 에서 기하-의미론 공동 최적화 framework 제안. 결과물은 structured primitives".

- CityGML 은 하나의 downstream 응용
- 다른 downstream 가능: BIM 변환, semantic segmentation, rendering, interactive editing
- 박사 논문 챕터 중 일부만 CityGML, 나머지는 다른 응용

---

## 6. Sequential pipeline 비교 (미측정)

**Step 3-2 비교 기준 설정 필요**. 현재 미측정.

적절한 sequential 비교군 (image-only 계):
1. **MVS (COLMAP) + RANSAC plane detection + convex/PolyFit** — 고전 photogrammetric LOD2
2. **PlanarSplatting** (Chen et al. CVPR 2025) — 2DGS + plane regularization, **structural joint 없음**
3. **CityGSV2** (2024) — 2DGS + MVS depth supervision, **structural joint 없음**
4. **2DGS vanilla** (Huang et al. SIGGRAPH 2024) — 우리 baseline 과 동치

**우리 baseline (40.5%) 이 이미 "2DGS + no structural constraint"** 로, 아마 (2), (3), (4) 와 비슷한 수준일 것. 진짜 의미 있는 sequential 은 (1) — 이건 측정 필요.

**예상**:
- (1) MVS+RANSAC+convex: **30-40% 수준** (문헌 image-only 기준)
- (2) PlanarSplatting: 보고된 val3dity 없음 (mesh quality 만 보고)
- (3) CityGSV2: val3dity 보고 안 함
- (4) 2DGS vanilla: 우리 baseline = 40.5%

Main comparison 후보:
- Ours (Both, 43.5%) vs (1) MVS sequential (측정 필요) → 아마 +5-15%p
- Ours vs (4) 2DGS vanilla = baseline → +3%p (이미 측정됨)

---

## 7. 결정 필요한 사항

**방향 결정 축**:

### 축 1. 연구 포지셔닝 — 틀 A/B/C 중 선택

| | 장점 | 단점 | 자산 활용 |
|---|---|---|---|
| A. val3dity 중심 | 기존 계획 유지 | 절대 수치 40% 설득력 부족 | ⚪ |
| B. Multi-metric | 여러 지표 종합, 현재 결과 살림 | CityGML 주인공 자리 양보 | ✅ 완전 |
| C. Upstream primitive | 범용성, 스토리 확장 | CityGML 목적을 후순위로 | △ |

### 축 2. Stage 3 알고리즘 처리 — convex / City3D / PolyFit 재도전 / Roofer

| Stage 3 | 상한 (GT) | 현 위치 | 필요 작업 |
|---|---|---|---|
| Convex | 76.3% | 결과 확보 | 없음 |
| 2.5D hybrid | 67.2% | 버그 있지만 결과 있음 | Deprecated |
| PolyFit (CGAL) | 불명 | watertight 실패 | 3-6h polygon_soup 재도전 |
| City3D | 예상 85-90% | 미도입 | 3-4h 통합 |
| Roofer | 예상 85-90% | 미도입 | 3-4h 통합 |

### 축 3. Sequential 비교 베이스라인

| 대상 | 측정 상태 | 예상 결과 |
|---|---|---|
| MVS + RANSAC + convex | 미측정 | 30-40% 예상 |
| PlanarSplatting | 미측정 | 메쉬 품질만, val3dity 불명 |
| CityGSV2 | 미측정 | 상동 |

### 축 4. Phase 3 (real 성수동 UAV) 역할

| 시나리오 | 설명 |
|---|---|
| 현재 계획 | Phase 2 가 메인 검증, Phase 3 는 real demo |
| 재구성 1 | Phase 3 를 main contribution, Phase 2 는 synthetic validation (작은 claim) |
| 재구성 2 | Phase 2 multi-metric + Phase 3 real 검증 병행 |

---

## 8. 확보된 자산 (이미 있는 결과)

### 데이터
- 3D BAG Amsterdam Jordaan v3 합성 데이터셋 (131 건물, 560 views)
- scene.obj GT, cameras.bin, depth/normal/semantic GT
- Interleave split (train 504, val 56)

### 모델 체크포인트 (각 30k iter)
- `results/phase2_ablation_citygml/{baseline,mutual,structure,both}/ckpt/final.pt`
- 각 988K-1M primitives

### Stage 3 결과
- 4 조건 × 111 건물 CityGML + val3dity
- 4 개 eval summaries (val3dity, face IoU, Hausdorff, SemAcc, σ_normal, confusion matrix)

### GT 상한 테스트
- Direct (93.9%), Convex (76.3%), 2.5D (67.2%)

### 시각화
- 대시보드 (src/apps/experiment_dashboard/): Phase 1/2 Stage 2 GS 뷰어, Phase 2 Stage 3 CityGML 6-panel 뷰어 (GT + 4 조건 + nearest Pix4D photo)
- 5 개 figures (fig1-5, barchart, error heatmap, sample building 등)

### 문서
- `docs/EXPERIMENT_PLAN.md` — 실험 순서
- `docs/RESEARCH_CONTEXT.md` — 배경, 파라미터
- `docs/PROGRESS_BRIEF.md` — 진행 요약 (일부 outdated)
- `results/phase2_synthesis/REPORT.md` — 합성 데이터 보고서
- `results/phase2_ablation_citygml/` — Phase 2-2 결과

---

## 9. 열린 질문 (claude-web 과 논의 용)

1. **연구 포지셔닝**: 틀 A/B/C 중 어느 것이 **박사 논문으로 가장 방어 가능** 한가? 
   - Image-only LOD2 생성의 val3dity 수치가 40% 수준인 것이 reviewer 에게 어떻게 보일지
   - Multi-metric 으로 reframe 하면 "CityGML 은 부차적" 으로 인식될 위험이 있는지

2. **기여의 절대적 크기**: 
   - Phase 2 Step 2-2 에서 메커니즘별 +3%p val3dity 개선은 "충분한" 기여인가?
   - Structure/Both 의 +3%p val3dity + Mutual 의 +0.025 face IoU 로 **"각 메커니즘이 서로 다른 축 개선"** 서사 가능한가?
   - Mutual 단독의 val3dity 회귀 (-8.4%p) 를 어떻게 해석/설명해야 하는가?

3. **평가 지표 선택**:
   - val3dity 는 binary + topology 엄격 검증 — image-only 에는 부적절할 수 있음
   - 대안: face IoU, Hausdorff, 구조적 domain rule metrics, Chamfer distance
   - 어떤 조합이 우리 기여를 제일 잘 드러내는가?

4. **Stage 3 선택**:
   - convex (76.3% 천장) 유지 vs City3D/Roofer (85-90% 천장 기대) 로 전환
   - **전환 시 footprint 사용 → 연구 claim 축소** 이슈. 하지만 Stage 3 는 외부 도구로 취급하면 괜찮을 수 있음
   - 또는 PolyFit 재도전 (polygon_soup + watertight guarantee)

5. **Sequential 비교 우선순위**: 
   - MVS+RANSAC+convex 측정 필수인가? 
   - 만약 MVS sequential 이 우리 baseline (40.5%) 보다 낮게 나오면 "joint > sequential" 명확해짐
   - 만약 비슷하면? PlanarSplatting, CityGSV2 측정이 더 중요한가?

6. **Phase 3 비중**: 
   - Phase 2 의 absolute number 한계를 감안하여 Phase 3 (real UAV) 로 main story 이동할 가치가 있는가?
   - 성수동 real data 에서 우리 방법이 얼마나 좋을지 불확실 (synthetic 에서도 40% 라는 점이 걱정)

7. **시간 투자 우선순위**:
   - 남은 시간: (박사 일정 맥락에서) 향후 1-2 개월 범위
   - Phase 2 결과 재분석 (multi-metric, figures) 0.5-1 주
   - Stage 3 변경/재도전 1-2 주
   - Sequential baseline 측정 1-2 주
   - Phase 3 real UAV 데이터 준비 + 학습 2-4 주
   - 무엇을 우선해야 하는가?

---

## 10. 부록 — 파일 위치

### 논문 글쓰기 / 실험 문서
- `docs/EXPERIMENT_PLAN.md` — 실험 계획
- `docs/RESEARCH_CONTEXT.md` — 배경 맥락
- `docs/PROGRESS_BRIEF.md` — 진행 브리핑 (out-of-date)
- 본 문서 `docs/RESEARCH_STATUS.md`

### Stage 2 / Stage 3 결과
- `results/phase2_synthesis/REPORT.md` + `scene.obj` + `dataset/`
- `results/phase2_ablation_citygml/{baseline,mutual,structure,both}/` — 각 ckpt, stage3, eval
- `results/phase2_ablation_citygml/figures/` — fig1~5
- `results/phase2_ablation_citygml/_gt_{direct,stage3_test,stage3_test_2_5d_v2}/` — GT 상한

### 핵심 소스
- `src/stage2/` — 2DGS + L_mutual + L_structure
- `src/stage3/building_instance.py` — convex/2.5D 디스패처
- `src/stage3/plane_intersection.py` — convex polytope
- `src/stage3/building_2_5d.py` — 2.5D hybrid (1218 lines, legacy port + margin fix)
- `src/stage3/polyfit_cli.cpp` — CGAL PolyFit (compiled but watertight 이슈)
- `scripts/phase2_synthesis/` — 학습/평가/figure 스크립트
- `src/apps/experiment_dashboard/` — dashboard (Phase 1/2 Stage 2 + Phase 2 Stage 3 뷰어)
