# 실험계획 (v6 — gsplat/2DGS 기반, Claude Code 실행용)

## 리포지터리 구조 (gsplat 라이브러리 의존)

gsplat은 pip install로 설치하는 라이브러리. fork가 아니라 의존성으로 사용.
우리 코드가 주체이고, gsplat은 렌더링 함수를 호출하는 의존성.

```
JointBuildGS/
├── CLAUDE.md
├── docs/
│   ├── EXPERIMENT_PLAN.md
│   └── RESEARCH_CONTEXT.md
├── requirements.txt                # gsplat, torch, etc.
├── src/
│   ├── stage1/                     # SfM/MVS + Grounded SAM (기존)
│   ├── stage2/
│   │   ├── model.py                # 2DGS 파라미터 정의 (c, n, s, f, color)
│   │   ├── renderer.py             # gsplat 호출 → RGB/depth/normal/semantic
│   │   ├── loss/
│   │   │   ├── data_fitting.py     # L_depth, L_normal, L_photo, L_nc
│   │   │   ├── semantic.py         # L_sem
│   │   │   ├── mutual.py           # L_mutual (메커니즘 1, intra)
│   │   │   └── structure.py        # L_structure (메커니즘 2, inter)
│   │   ├── grouping.py             # 메커니즘 2 그룹핑
│   │   ├── densification.py        # split/clone/prune + 그룹 연동
│   │   ├── dataloader.py           # COLMAP 데이터 로딩
│   │   └── train.py                # 학습 루프, warmup, 스케줄
│   └── stage3/
│       ├── clustering.py
│       ├── plane_intersection.py
│       ├── building_instance.py
│       ├── ground_surface.py
│       └── citygml_export.py
├── scripts/
│   ├── synthetic_a/
│   ├── synthetic_b/
│   └── comparison/
├── configs/
│   ├── baseline.yaml
│   ├── joint.yaml
│   └── joint_structure.yaml
├── data/
│   ├── seongsu/
│   ├── 3dbag/
│   └── synthetic/
├── results/
│   ├── phase1_setup/
│   ├── phase1_vanilla/
│   ├── phase1_semantic/
│   ├── phase1_mutual/
│   ├── phase1_integration/
│   ├── phase2_baseline/
│   ├── phase2_joint/
│   ├── phase2_structure/
│   ├── phase3_citygml/
│   ├── synthetic_a/
│   ├── synthetic_b/
│   └── comparison/
└── legacy/                         # PlanarSplatting 예비 실험 보존
```

## 현재 상태

| 항목 | 상태 | 비고 |
|------|------|------|
| Stage 1 (SfM/MVS + Grounded SAM) | 완료 | 성수동 100장, seg GT |
| PlanarSplatting 예비 실험 | 완료 | L_mutual 효과 확인, 항공 밀착 실패 |
| Synthetic A (Stage 3 단독) | 완료 | 법선 지배성 발견, base 무관 |
| gsplat/2DGS 기반 파이프라인 | **미착수** | ← 현재 시작점 |

## 실행 순서

```
Phase 1: gsplat 기반 파이프라인 구축
  Step 1-0: 리포지터리 셋업 + 기존 자산 마이그레이션
  Step 1-1: gsplat 기반 2DGS Vanilla 학습
  Step 1-2: Semantic head + L_sem
  Step 1-3: L_mutual 이식 + Gravity
  Step 1-4: 통합 검증

Phase 2: Stage 2 실험 — Ablation
  Step 2-1: Baseline 학습
  Step 2-2: Joint (메커니즘 1)
  Step 2-3: L_structure 구현 (메커니즘 2)
  Step 2-4: Joint+Structure (메커니즘 1+2)

Phase 3: Stage 3 + 비교 실험
  Step 3-1: Stage 3 → CityGML
  Step 3-2: Synthetic B
  Step 3-3: City3D 비교
  Step 3-4: 종합
```

---

## Phase 1: gsplat 기반 파이프라인 구축

### Step 1-0: 리포지터리 셋업 + 기존 자산 마이그레이션

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-0을 진행해줘.

목표: 새 리포지터리 구조 생성 + 기존 자산 마이그레이션.

=== Part A: 리포지터리 생성 ===
EXPERIMENT_PLAN.md의 리포지터리 구조대로 디렉토리 생성.
CLAUDE.md를 루트에 배치. EXPERIMENT_PLAN.md를 docs/에 배치.

=== Part B: 기존 자산 마이그레이션 ===
기존 리포지터리 경로: /media/innopam/InnoPAM-8TB/hwiyoung/code/PlanarSplatting

1. Synthetic A:
   - 기존 코드(generate_synthetic_primitives.py, add_noise_to_primitives.py, Stage 3 실행 코드)를 scripts/synthetic_a/로 복사
   - 기존 결과(val3dity, 면 IoU, Hausdorff, REPORT.md)를 results/synthetic_a/로 복사
2. Stage 3 코드를 src/stage3/로 분리 정리 (clustering, plane_intersection, building_instance, ground_surface, citygml_export)
3. PlanarSplatting 예비 실험 전체를 legacy/로 보존 (L_mutual, L_sem 구현 참고용)
4. Stage 1 출력물(COLMAP 결과, Grounded SAM GT)을 data/seongsu/에 배치
5. 3D BAG 데이터를 data/3dbag/에 배치

=== Part C: 의존성 설정 ===
requirements.txt 생성:
- gsplat (pip install gsplat)
- torch, torchvision
- numpy, scipy, open3d, trimesh
- lxml (CityGML XML)
- 기타 필요 라이브러리

=== Part D: 검증 ===
Synthetic A를 새 위치에서 실행하여 기존 결과 재현 확인.

results/phase1_setup/REPORT.md 작성.
```

### Step 1-1: gsplat 기반 2DGS Vanilla 학습

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-1을 진행해줘.

목표: gsplat 라이브러리를 사용하여 성수동 데이터에서 2DGS vanilla 학습 파이프라인 구축 및 확인.

=== Part A: gsplat 기반 학습 파이프라인 구축 ===
gsplat의 examples/ 스크립트를 참고하되, 우리 코드 구조에 맞게 작성.

1. src/stage2/model.py:
   - 2DGS 프리미티브 파라미터 관리 (c_i, tangent_u/v, s_i, opacity, SH)
   - 초기화: COLMAP 포인트 클라우드에서
   - n_i = normalize(t_u × t_v) 함수

2. src/stage2/renderer.py:
   - gsplat의 rasterization 함수 호출
   - RGB, depth, normal 렌더링
   - from gsplat import rasterization (또는 해당 API)

3. src/stage2/loss/data_fitting.py:
   - L_depth = L1(D_render, D_MVS)
   - L_normal = 1 - cos(n_render, n_MVS)
   - L_photo = (1-λ)·L1 + λ·(1-SSIM), λ=0.2
   - L_nc = 1 - cos(n_render, n_depth_derived)
     * n_depth_derived: 렌더링 depth map의 인접 픽셀 finite difference cross product

4. src/stage2/densification.py:
   - gsplat의 densification strategy 활용 (또는 직접 구현)
   - split/clone/prune

5. src/stage2/dataloader.py:
   - COLMAP 출력 로딩 (카메라, 이미지, 포인트 클라우드)
   - MVS depth/normal 로딩

6. src/stage2/train.py:
   - 학습 루프: forward → loss → backward → optimizer step → densification
   - TensorBoard 로깅

=== Part B: 성수동 Vanilla 학습 ===
L_photo + L_depth + L_normal + L_nc, 30000 iter.
평가: PSNR, Depth MAE, Normal cos.

=== Part C: 항공 적응 확인 ===
Coverage, px/prim 측정.
PlanarSplatting(legacy/) 결과 대비 밀착 개선 확인.

=== 시각적 산출물 ===
1. RGB/Depth/Normal 렌더링 (4뷰 이상)
2. 프리미티브 3D PLY
3. Coverage 히트맵
4. PlanarSplatting vs gsplat/2DGS 비교 표

results/phase1_vanilla/REPORT.md 작성. CLAUDE.md 업데이트.
```

### Step 1-2: Semantic Head + L_sem

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-2를 진행해줘.

목표: 2DGS에 semantic head(f_i, K=4) 추가 + L_sem 구현.

=== Part A: Semantic Head ===
src/stage2/model.py 수정:
- 각 Gaussian에 f_i ∈ R^4 파라미터 추가. 초기화: uniform.
- split/clone: 부모 f_i 복사. prune: 함께 제거.

src/stage2/renderer.py 수정:
- gsplat의 N-D feature 렌더링 활용.
  gsplat은 colors shape=[N,D]를 네이티브 지원하므로, f_i를 colors로 전달하여 semantic map 렌더링.
  RGB와 semantic을 별도 forward pass 또는 채널 결합으로 렌더링.
- softmax 적용하여 픽셀별 class 확률 생성.

=== Part B: L_sem ===
src/stage2/loss/semantic.py:
- CrossEntropyLoss(ignore_index=0)
- GT: data/seongsu/ Grounded SAM segmentation
- Gradient 격리 검증: L_sem → f_i에만 gradient, c_i/n_i/s_i/color에는 gradient 없음

=== Part C: 학습 + 평가 ===
L_photo + L_depth + L_normal + L_nc + L_sem, 30000 iter.
기하 지표 유지 확인 + mIoU, per-class IoU 측정.

=== 시각적 산출물 ===
1. Semantic map 렌더링 (class별 색상, 4뷰)
2. 프리미티브 PLY (class별 색상)
3. Gradient 격리 검증 로그

results/phase1_semantic/REPORT.md 작성. CLAUDE.md 업데이트.
```

### Step 1-3: L_mutual 이식 + Gravity

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-3을 진행해줘.

목표: L_mutual을 gsplat/2DGS에 이식 + gravity 추정 연결.

=== Part A: Gravity 추정 ===
Grounded SAM GT terrain 영역의 MVS 법선 평균 = UP → gravity = -UP.
학습 전 1회 계산. Fallback: terrain 부족 시 경고.

=== Part B: L_mutual 이식 ===
legacy/ 참고. src/stage2/loss/mutual.py에 구현.
핵심 변경: n_i = normalize(t_u × t_v) (gsplat 2DGS tangent에서).
L_mutual = Σ_i [p_wall·(n_i·e_g)² + p_roof·relu(τ-(n_i·e_g)²)² + p_terrain·(1-|n_i·e_g|)² + L_height]
Warmup: 0~N/3에서 λ_m=0 (비율 기반, N에 따라 자동 조정).

=== Part C: Gradient 검증 ===
∂L_mutual/∂n_i ≠ 0 (tangent까지 역전파), ∂L_mutual/∂f_i ≠ 0, ∂L_mutual/∂c_i (L_height 높이만), ∂L_mutual/∂s_i = 0.
Detach mode 구현.

=== Part D: Smoke Test ===
10 iter: NaN 없음, loss 감소.

=== 시각적 산출물 ===
1. Gravity 시각화
2. Gradient 검증 로그

results/phase1_mutual/REPORT.md 작성. CLAUDE.md 업데이트.
```

### Step 1-4: 통합 검증

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 1-4를 진행해줘.

목표: 전체 Stage 2 파이프라인 통합 검증 (L_structure 제외).

=== 학습 ===
L_depth + L_normal + L_nc + L_sem + L_photo + L_mutual (warmup), 5000 iter.

=== 비교 ===
Step 1-1(vanilla) vs Step 1-2(+sem) vs Step 1-4(+mutual).
PlanarSplatting 예비 결과 대비 coverage/밀착 개선 확인.

=== Go/No-Go ===
Go: coverage > 80%, wall normal 개선, mIoU > 0.75.
No-Go: gsplat 파라미터 조정, 또는 AGS/ULSR-GS 항공 메커니즘 참고.

=== 시각적 산출물 ===
1. 3조건 비교 표 (vanilla / +sem / +mutual)
2. Normal/Semantic 비교 렌더링 (동일 뷰)
3. Coverage 히트맵 (PlanarSplatting vs gsplat/2DGS)
4. Wall 법선 수직도 히스토그램

results/phase1_integration/REPORT.md 작성. CLAUDE.md 업데이트.
```

---

## Phase 2: Stage 2 실험 — Ablation

### Step 2-1: Baseline

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 2-1을 진행해줘.

목표: Baseline 학습 (λ_m=0, λ_str=0), 30000 iter.
평가: PSNR, Depth MAE, Normal cos, mIoU, per-class IoU, Wall 법선 수직도.
CityGML 전제 조건 측정: wall σ_normal.

=== 시각적 산출물 ===
렌더링 8뷰, PLY, Wall 법선 히스토그램, Coverage.

results/phase2_baseline/REPORT.md 작성. CLAUDE.md 업데이트.
```

### Step 2-2: Joint (메커니즘 1)

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 2-2를 진행해줘.

목표: Joint = Baseline + L_mutual, 30000 iter, warmup N/3부터.
Joint vs Baseline 비교.
조건부: Joint < Baseline이면 Joint-GTOnly, Joint-Weak 추가.

=== 시각적 산출물 ===
Baseline vs Joint side-by-side, Wall 법선 히스토그램 비교, Δ 막대그래프.

results/phase2_joint/REPORT.md 작성. CLAUDE.md 업데이트.
```

### Step 2-3: L_structure 구현 (메커니즘 2)

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 2-3을 진행해줘.

목표: 메커니즘 2(inter-primitive 구조 정렬) 구현.

=== Part A: 그룹핑 ===
src/stage2/grouping.py:
- 입력: 전체 프리미티브의 f_i(→argmax class), n_i, c_i, s_i
- 조건: (1) 동일 class, (2) 법선 cos > threshold, (3) 공간 근접 < threshold
- 출력: group_id, 그룹별 대표 평면 (n_k, d_k) = 가중 평균(s_i 기반)
- 매 T=500 iter 재계산
- Density control 연동: split/clone → 부모 group_id, prune → 탈퇴

=== Part B: L_structure ===
src/stage2/loss/structure.py:
- L_normal_align = Σ_k Σ_{i∈G_k} (1 - n_i·n_k)² → n_i gradient, n_k detach
- L_coplanar = Σ_k Σ_{i∈G_k} (n_k·c_i + d_k)² → c_i gradient, n_k/d_k detach
- L_structure = λ_na·L_normal_align + λ_cp·L_coplanar
- Warmup: 2N/3부터 (비율 기반)

=== Part C: 검증 ===
Gradient: ∂L_na/∂n_i ≠ 0, ∂L_cp/∂c_i ≠ 0, ∂L_str/∂f_i = 0.
Smoke test: 10 iter + 그룹 재계산 1회.

=== 시각적 산출물 ===
그룹핑 PLY (그룹별 색상), Gradient 로그, 그룹 통계.

results/phase2_structure/REPORT.md 작성. CLAUDE.md 업데이트.
```

### Step 2-4: Joint+Structure (메커니즘 1+2)

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 2-4를 진행해줘.

목표: Joint+Structure = Baseline + L_mutual + L_structure, 30000 iter.
L_mutual N/3부터, L_structure 2N/3부터 (비율 기반).

=== 평가 ===
Joint+Structure vs Joint vs Baseline.
면 단위 일관성: σ_normal_intra, σ_coplanar.
Synthetic A 매핑: σ_normal → 예상 val3dity.

=== 시각적 산출물 ===
3조건 비교 표, 그룹핑 시각화, σ_normal_intra 히스토그램,
Coplanarity 분포, Synthetic A에 실측 세로선, 렌더링 3조건 비교.

results/phase2_structure/REPORT.md에 추가. CLAUDE.md 업데이트.
```

---

## Phase 3: Stage 3 + 비교 실험

### Step 3-1: Stage 3 → CityGML

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 3-1을 진행해줘.

목표: Baseline/Joint/Joint+Structure → Stage 3 → CityGML + val3dity.

=== 시각적 산출물 ===
CityGML 3D, val3dity 오류 하이라이트, 건물별 품질 표,
이미지→프리미티브→CityGML 3단계 비교, 3조건 val3dity 막대그래프.

results/phase3_citygml/REPORT.md 작성.
```

### Step 3-2: Synthetic B

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 3-2를 진행해줘.

목표: gsplat/2DGS 기반 Synthetic B.

=== 합성 렌더링 ===
3D BAG GT → mesh → 카메라(이상적/oblique/nadir/뷰 감소) → 렌더링.

=== 조건 ===
기본: 이상적+clean. 노이즈: depth/seg. 카메라: 이상적/oblique/nadir/50%/25%.
각 조건: Stage 2(Joint+Structure) → Stage 3 → GT 비교.

=== 시각적 산출물 ===
조건별 CityGML, val3dity 막대그래프, 카메라별 비교 표.

results/synthetic_b/REPORT.md 작성.
```

### Step 3-3: City3D 비교

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 3-3을 진행해줘.

목표: 순차 vs 공동최적화 비교.
(a) 영상+순차+footprint, (b) 영상+순차-footprint, (c) 제안 방법, (d) LiDAR upper bound.
val3dity, 면 IoU, 의미론, 처리 시간.

=== 시각적 산출물 ===
Side-by-side, val3dity 4조건, 의미론 비교, 시간 표.

results/comparison/REPORT.md 작성.
```

### Step 3-4: 종합

**프롬프트:**
```
docs/EXPERIMENT_PLAN.md의 Step 3-4를 진행해줘.

목표: 전체 결과 종합 + 논문용 최종 산출물.
기여 1 증거: ablation (2-2, 2-4). 기여 2 증거: Synthetic A + 비교. 기여 3 증거: (b) vs (c).
최종 표, 그래프, CityGML 결과, 실패 분석.

results/final/REPORT.md 작성.
```

---

## REPORT.md 템플릿

```markdown
# [Phase/Step] 결과 보고

## 수행 일시

## 수행 작업 요약

## 정량 지표
| 지표 | 값 | 이전 | 변화 |
|------|-----|------|------|

## 시각적 산출물 체크리스트
- [ ] 산출물 1

## Go/No-Go

## 이슈 및 해결

## 다음 단계
```
