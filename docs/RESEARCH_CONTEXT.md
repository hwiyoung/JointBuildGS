# Research Context — JointBuildGS

이 문서는 Claude Code가 구현/실험 시 참조하는 상세 기술 맥락이다.
프로젝트 개요와 규칙은 CLAUDE.md, 실험 순서와 프롬프트는 EXPERIMENT_PLAN.md 참조.

---

## 1. 연구 배경

### 1.1 문제 정의
건물의 구조적 3D 모델(소수 평면 + 면 단위 의미론 + watertight solid)을 영상에서 생성한다.
기존 방법은 순차 파이프라인을 따르며, 세 그룹의 실패 모드를 가진다.

| 그룹 | 실패 모드 | 미분 가능 해법 | 대응 메커니즘 |
|------|----------|-------------|-------------|
| A: 구조 추출 정확도 | 오병합, 누락, 교차선 | 동시 최적화 + 피드백 | 메커니즘 2 (inter) |
| B: 도메인 지식 미반영 | 건축 규칙 위반 | loss에 직접 부과 | 메커니즘 1 (intra) |
| C: 오류 교정 불가 | 일방향 전파 | 역전파 상호 수정 | 전체 프레임워크 |

### 1.2 핵심 연구 질문
"왜 RANSAC 대신 미분 가능 최적화로 구조를 추출하는가?"

### 1.3 LiDAR 대비 논거
층위 1 (방법론): 순차 파이프라인 실패 모드는 입력 품질과 무관.
층위 2 (입력): 항공 LiDAR는 벽면 미관측 → 외부 풋프린트 + 수직 가정 필요.
층위 3 (확장): LiDAR → LoD3 시 별도 데이터 필요. 본 방법은 연속 확장 가능.

---

## 2. 파이프라인

### Stage 1: SfM/MVS + 2D Segmentation
- COLMAP SfM/MVS → 카메라 포즈, 포인트 클라우드, D_MVS, n_MVS
- Grounded SAM 2 → 2D segmentation GT (K=4)
- Gravity: terrain MVS 법선 평균 = UP → e_g = -UP. 학습 전 1회.

### Stage 2: 구조 인식 공동 최적화
- gsplat/2DGS + L_mutual(intra) + L_structure(inter)

### Stage 3: CityGML 변환
6단계: 분류 → 클러스터링 → 평면 교차 → 건물 분리 → GroundSurface → val3dity.

---

## 3. 프리미티브 (G_i)

| 변수 | 차원 | 의미 |
|------|------|------|
| c_i | (N,3) | 중심 |
| t_u, t_v | (N,3)×2 | tangent 벡터 |
| s_i | (N,2) | in-plane scale |
| opacity_i | (N,1) | 불투명도 |
| f_i | (N,4) | semantic logits |
| sh_i | (N,C) | SH 계수 |

법선: n_i = normalize(t_u × t_v).

렌더링 (gsplat): RGB, Depth, Normal, Semantic을 각각 alpha-blending. gsplat은 colors=[N,D] 네이티브 지원.

Semantic class (K=4): BG(0, ignore), Roof(1), Wall(2), Terrain(3, context).

---

## 4. 손실 함수

### 전체
```
L = L_depth + L_normal + λ_nc·L_nc + λ_s·L_sem + λ_p·L_photo + λ_m·L_mutual + λ_str·L_structure
```

### L_depth
(1/|M|) Σ |D_render(p) - D_MVS(p)|. c_i에 강한 직접 gradient.

### L_normal
(1/|M|) Σ (1 - n_render · n_MVS). n_i에 직접 gradient.

### L_photo
(1-λ)·L1 + λ·(1-SSIM), λ=0.2.

### L_nc (Normal Consistency)
(1/|P|) Σ (1 - n_render · n_depth).
- n_render: 프리미티브 법선의 alpha-blending. tangent에서 유도.
- n_depth: 렌더링 depth map의 인접 픽셀 finite difference cross product. c_i에서 유도.
- n_MVS: Stage 1 GT normal.
목적: depth와 normal이 독립 파라미터이므로 모순 방지.

### L_sem
CrossEntropyLoss(softmax(f_render), GT_seg, ignore_index=0). f_i에만 gradient.

### L_mutual (메커니즘 1, Intra-primitive)
```
L_mutual = Σ_i [p_wall·(n_i·e_g)² + p_roof·relu(τ-(n_i·e_g)²)² + p_terrain·(1-|n_i·e_g|)² + L_height]
```
p_c = softmax(f_i). e_g = gravity (사전 추정).

양방향 원리: p_c × 기하 오차의 곱.
- 의미론→기하학: p_c 높으면 → 기하 오차 gradient 증폭 → n_i 교정.
- 기하학→의미론: 기하 오차 작으면 → p_c 높이는 것이 유리 → f_i 교정.
L_sem이 독립적으로 f_i를 GT 방향으로 강제하여 균형.

Gradient: n_i, f_i 양방향. c_i(L_height 높이만). s_i 없음.
Warmup: 0~N/3에서 λ_m=0.

### L_structure (메커니즘 2, Inter-primitive)
매 T iter 그룹핑 (class + 법선 cos>th + 공간 근접). 대표 평면 Π_k = (n_k, d_k) 가중 평균.

L_normal_align = Σ_k Σ_{i∈G_k} (1-n_i·n_k)². n_i gradient, n_k detach.
L_coplanar = Σ_k Σ_{i∈G_k} (n_k·c_i+d_k)². c_i gradient, n_k/d_k detach.
L_structure = λ_na·L_normal_align + λ_cp·L_coplanar.

L_coverage(s_i): 후보. densification 대비 검증.

**f_i에 직접 gradient 없음.** 그룹 할당 = argmax(f_i) 이산 연산 → ∂L_structure/∂f_i = 0.
f_i 교정은 메커니즘 1(L_mutual) 담당. 간접 피드백: 매 T iter 그룹 재할당.

**핵심: 메커니즘 1과의 동시 작용.**
매 iteration에서 n_i에 대한 gradient:
∂L/∂n_i = ... + ∂L_mutual/∂n_i + ∂L_normal_align/∂n_i
하나의 파라미터에 도메인 규칙("벽이니까 수평") + 면 단위 정렬("같은 면이니까 같은 방향")이 동시 작용.
메커니즘 2가 n_i 정렬 → 메커니즘 1이 정렬된 n_i로 f_i 교정 → 교정된 f_i가 다음 그룹 재할당에 반영.
이 동시 작용 + 주기적 재할당의 순환이 순차 파이프라인과의 근본적 차이.

**s_i에 별도 제약 없음.** Stage 3에서 CityGML 폴리곤 경계는 인접 대표 평면을 확장하여 교차선으로 결정되므로 s_i에 의존하지 않음. s_i는 데이터 정합 손실과 densification으로 조정. 항공 2DGS(AGS, ULSR-GS)도 s_i에 별도 제약 미부과.

대표 법선 정확도 위험 → 안전장치: warmup(2N/3 이후), 재계산, 가중 평균.
Warmup: 2N/3 이후 활성화.

---

## 5. 학습 전략

### Warmup
| 구간 | Iteration | 활성 손실 |
|------|----------|----------|
| 초기 | 0~N/3 | L_depth+L_normal+L_nc+L_sem+L_photo |
| 중기 | N/3~2N/3 | +L_mutual |
| 후기 | 2N/3~N | +L_structure |

### 하이퍼파라미터 (초기값)
| 파라미터 | 값 | 비고 |
|---------|-----|------|
| λ_nc | 0.01 | 2DGS 참고 |
| λ_s | 0.1 | 예비 실험 |
| λ_p | 1.0 | 표준 |
| λ_m | 0.1 | warmup 후 |
| λ_na | TBD | 실험적 |
| λ_cp | TBD | 실험적 |
| τ (L_slope) | 0.15 | 예비 실험 |
| T (그룹 주기) | 500 | 실험적 |
| N (총 iter) | 30000 | 정식 |

---

## 6. 평가 지표

| 지표 | 수식/도구 | 레퍼런스 |
|------|----------|---------|
| PSNR | -10·log10(MSE) | 3DGS, CityGSV2 |
| SSIM | structural similarity | 3DGS, CityGSV2 |
| LPIPS | learned perceptual | 3DGS, CityGSV2 |
| Depth MAE | mean(\|D_render-D_GT\|) | 2DGS |
| Normal cos | mean(n_render·n_GT) | 2DGS |
| F1 (0.5m, 1.0m) | precision-recall @ threshold | CityGSV2, AGS, ULSR-GS |
| Chamfer Distance | bidirectional nearest-neighbor | CityGSV2, AGS |
| Wall 수직도 | wall 중 \|n·e_g\|<sin(10°) 비율 | 본 연구 |
| mIoU | mean(TP/(TP+FP+FN)) | AlignGS |
| val3dity | Ledoux(2019) | PLANES4LOD2 |
| 면 IoU | 생성 vs GT | Point2Building |
| Hausdorff | 최대 거리 | City3D |
| σ_normal_intra | 그룹 내 법선 분산 | 본 연구 |
| σ_coplanar | 그룹 내 coplanarity 오차 | 본 연구 |

---

## 7. 실험 조건

### Ablation (4조건)
| 조건 | 구성 | 검증 |
|------|------|------|
| Baseline | L_photo+L_depth+L_normal+L_nc+L_sem | 메커니즘 없음 |
| Mutual only | +L_mutual | 메커니즘 1 단독(intra) |
| Structure only | +L_structure | 메커니즘 2 단독(inter) |
| Both | +L_mutual+L_structure | 동시 작용 |

핵심 비교:
- Structure only vs Both: 순환 효과 검증. Both에서 better면 "메커니즘 1의 양방향 gradient가 메커니즘 2의 그룹핑 품질 개선".
- Mutual only vs Both: 면 단위 정렬의 추가 가치.
- Both vs Mutual+Structure 합: 시너지/독립/간섭.

### 비교
(a) 영상+순차+footprint, (b) 영상+순차-footprint, (c) 제안, (d) LiDAR upper bound.

### Synthetic A (완료)
법선 지배성: 20°→val3dity -53%p, 분류 30%→-10%p. 2위의 5배.

### Synthetic B
이상적+clean 기본. 노이즈: depth/seg. 카메라: 이상적/oblique/nadir/뷰 감소.

---

## 8. 데이터

### 성수동
180장 oblique (DJI, 70m, GSD~1cm). COLMAP 100장. data/seongsu/.

### 3D BAG
LOD2.2. 20개(개별) + 구역 단위(도시 규모). data/3dbag/.

---

## 9. 용어 규칙

| 사용 | 미사용 |
|------|--------|
| 미분 가능 렌더링 | 뉴럴 렌더링 |
| 미분 가능 렌더링 기반 3D 재구성 | 뉴럴 3D 재구성 |
| gsplat / 2DGS | PlanarSplatting (legacy만) |
| G_i | P_i |
| intra-primitive (메커니즘 1) | — |
| inter-primitive (메커니즘 2) | — |
| 벽 법선 수평(gravity에 수직) | 벽 법선 수직 |
| L_nc | L_geo |
| Stage (파이프라인) | Phase (실험 순서만) |

---

## 10. 레퍼런스

### 건물 구조 추출
- PolyFit (Nan & Wonka, 2017), City3D (Huang et al., 2022), KSR (2020), Point2Building (2024), 3DBAG, PLANES4LOD2 (2024), SAT2BUILDING (2025)

### 미분 가능 렌더링
- 3DGS (Kerbl et al., 2023), 2DGS (Huang et al., 2024), PGSR (2024), PlanarSplatting (2025), gsplat

### 항공/도시
- AGS (Wu et al., 2024), ULSR-GS (Li et al., 2025), CityGaussianV2

### 기하-의미론 연계
- AlignGS (2025), NeRBuilder (2025), IGGT (2025), PCGrad (2020), CAGrad (2021)

### 미분 가능 구조 추출
- DSAC (2017), SPFN (2019), PARSAC (2024)

### 분리 논리
- City3D: data fitting vs structural prior
- PointNet++ (Qi et al., 2017): local vs hierarchical

### CityGML/검증
- CityGML 2.0/3.0, val3dity (Ledoux, 2019), ISO 19107

### RANSAC 실패
- Tarsha-Kurdi et al. (2007), Canaz Sevgen (2020), PARSAC (2024)

---

## 11. 예비 실험 (PlanarSplatting, legacy/)

### L_mutual 효과 (Synthetic B)
Clean wall normal 8.9°→3.8°, Noisy 9.0°→4.3°. 밀착 실패(coverage 6-26%) → gsplat 변경 근거.

### 법선 지배성 (Synthetic A)
법선 20° → val3dity -53%p. 분류 30% → -10%p. 2위의 5배.

### 성수동
mIoU=0.81. L_mutual gravity 미보정 보류. Stage 3: 11 instance, non-watertight.

---

## 12. gsplat 2DGS 구현 주의사항

실제 구현 중 발견한 gsplat 1.4.0 + 2DGS 관련 함정. Claude Code 참조용.

### 12.1 Densification gradient key
gsplat 2DGS는 gradient를 `gradient_2dgs` 키로 전달하지만, DefaultStrategy의 `key_for_gradient` 기본값은 `"means2d"`. 기본값 사용 시 grow가 0회 실행되어 프리미티브가 prune만 됨.
**수정:** `DefaultStrategy(..., key_for_gradient="gradient_2dgs")` 명시.

### 12.2 Scales shape
`rasterization_2dgs`는 scales를 (N,3)으로 요구 (dim2 ≈ 0으로 설정). (N,2)로 전달 시 오류.

### 12.3 Distortion loss weight
Depth distortion loss의 weight가 과도하면 total loss를 지배함. 초기값으로 w_distort=100은 문제. 0 또는 낮은 값으로 시작 후 조정.

### 12.4 L_nc 구현
gsplat의 `render_normals_from_depth`는 shape 불일치 이슈 있음. 자체 구현 권장:
- `depth_to_normal(D_render)`: 인접 픽셀 finite difference → cross product
- n_render는 gsplat이 world-frame으로 변환해서 반환 (추가 변환 불필요)

### 12.5 Densification sync
gsplat strategy가 params dict를 교체해도 우리 model의 파라미터에 자동 반영 안 됨.
**수정:** `_sync_params_to_model()` 호출로 명시적 동기화.

### 12.6 Render normals 좌표계
`render_normals`는 이미 world-frame. `render_normals_from_depth`와 비교 시 좌표계 일치 확인.

---

## 13. Step 1-1 Smoke Test 결과 (2026-04-16)

### 환경
- Docker: jointbuildgs:dev (CUDA 12.1.1 + torch 2.4.1 + gsplat 1.4.0)
- GPU: RTX 3090
- Data: MatrixCity Small City Aerial (5,621장, CityGSV2 COLMAP sparse)

### Smoke test (3k iter, photo only)
| 지표 | 값 | 참고 |
|------|-----|------|
| Train PSNR | 20.60 | CityGSV2 baseline 21.35 (30k) |
| N (primitives) | 3.8M → 7.9M | grow 정상 작동 확인 |

### 의의
- gradient_2dgs 버그 수정이 핵심
- 3k만에 CityGSV2 30k baseline(21.35)에 근접
- 30k 본 학습에서 baseline 도달/초과 기대
- 파이프라인 구현이 레퍼런스 수준으로 작동함을 확인

### 이전 시도 (실패)
성수동 30k, eval PSNR 16.3 dB, N 62k. gradient_2dgs 버그로 grow 미작동이 원인. 수정 후 MatrixCity에서 정상 확인.

---

## 14. Phase 2-2 핵심 발견 (2026-04-25)

### 14.1 Stage 2 4조건 결과
| 조건 | PSNR | Wall vert | σ_normal_intra | σ_coplanar |
|------|------|----------|---------------|-----------|
| Baseline | 40.35 | 28.0% | 14.74° | 1.91m |
| Mutual | 40.93 | **79.3%** | 12.63° | 1.84m |
| Structure | 40.96 | 28.4% | 14.88° | 1.86m |
| Both | 39.81 | **79.4%** | 12.99° | 2.01m |

### 14.2 Stage 3 4조건 결과 (convex polytope)
| 조건 | val3dity | face IoU | sem acc |
|------|---------|---------|---------|
| Baseline | 40.5% | 0.213 | 21.1% |
| Mutual | **32.1%** ↓ | **0.238** ↑ | 20.0% |
| Structure | **43.5%** ↑ | 0.220 | **21.8%** |
| Both | **43.5%** ↑ | 0.230 | 19.5% |

### 14.3 확인된 문제 (C1, C2, C3)

**C1: Mutual val3dity 회귀.**
Post-bbox-fix: -3.8%p (pre-fix -8.4%p, 절반은 bbox 버그). 잔존 회귀의 가설: D'(단순 건물 과조정), E(204 orientation 에러 증가).
v3의 dominant 가설(Stage 3 clustering over-merge)은 post-fix에서 Mutual 203=52, Baseline 54로 유사 → 부분 부정.

**C2: Stage 2 group(G1)과 Stage 3 surface의 unit mismatch.**
Stage 2 grouping.py: voxel hash(0.05m) + 12 dir bin = **patch 단위** (건물당 ~154개).
Stage 3 clustering.py: hierarchical clustering(cos>0.92) = **surface 단위** (건물당 ~7개).
Track 1(Stage 2 group 직접 전달) 시도 → patch 154개를 surface로 오인하여 실패.
**단순 인터페이스 정렬이 아니라 grouping 정의 자체가 문제 (G1 vs G2).**

**C3: L_normal_align 효과 소실 — 3 component 분해.**
- **C3a (photo redundancy, 측정 입증):** L_normal_align 활성화(step 20k)에서 이미 loss 0.0002. gradient L_mutual의 1/135. photo+L_normal이 normal을 이미 정렬(cos 0.984).
- **C3b (patch unit):** G1의 5cm patch가 원래 동질적 → L_normal_align이 intra-patch smoothing에 그침. Across-patch/surface 단위 정합(corner tilt 등) 못 잡음.
- **C3c (cycle 부재):** Cycle 4고리 모두 약함 (§14.4 참조).

### 14.4 Cycle 검증 결과 + 시너지 미입증 근본 원인

**Cycle 4고리 측정 (G1 위에서):**

| 고리 | 검증 방법 | 결과 |
|------|---------|------|
| 1. L_structure → n_i 정렬 | Loss magnitude | L_structure : L_mutual = **1 : 135** → 약함 |
| 2. 정렬된 n_i → f_i 교정 | L_mutual 수식 분석 | (n·e_g)² 작아질수록 ∂L_mut/∂f_i 작아짐 → **정렬되면 교정 비활성화** |
| 3. f_i 변경 → 그룹 재할당 | f_i argmax change | step 25k→30k Structure 0.45%, Both 0.29% → **trigger 없음** |
| 4. 그룹 변동 | n_groups 통계 | CV 2.01%, consecutive change 0.007% → **거의 정적** |

**결론:** G1 위에서 thesis의 "동시작용 cycle"이 4고리 모두 약함. cycle claim 미입증.

**근본 원인 3가지:**
1. **C3a (photo redundancy):** L_normal이 이미 n_i 정렬 → 고리 1 끊김.
2. **C3b (patch unit):** G1의 5cm patch가 동질적 → L_normal_align이 intra-patch smoothing에 그침.
3. **G1 grouping이 위치 기반:** f_i 변경이 voxel hash에 영향 안 줌 → 고리 3,4 끊김.

**G2(surface 단위)로 전환 시 고리 3,4 해소 가능:** f_i(class)가 grouping 조건이므로 f_i 변경이 직접 그룹 재할당을 trigger. G2에서 cycle 재검증 필요.
C3a는 G2로도 해소 안 됨. Real UAV(Phase 3)에서 L_normal 약해지면 고리 1도 복원 가능.

### 14.5 Stage 3 천장
| 방식 | val3dity | 비고 |
|------|---------|------|
| GT direct (topology 보존) | 93.9% | 절대 상한의 lower bound |
| GT + convex polytope (post-bbox-fix) | ~~96.2%~~ | **GT_convex reference 오류 — 절반 높이로 축소. 무효.** |
| GT + convex polytope (pre-bbox-fix) | ~~76.3%~~ | bbox 버그. 무효. |
| 우리 best (Structure/Both) | 55.0% | GT direct 93.9% 대비 -38.9%p 격차 |
| val3dity 203 (non-planar) | 95%+ | dominant failure mode |

**GT_convex reference 오류 발견 (v3):**
gt_stage3_test.py에서 GT를 convex polytope 통과시켰을 때, 131건물 중 88%(115건물)가 절반 이하 높이로 축소됨. 평균 비율 0.55-0.57. 원인 미확정(process_building의 face merge 로직 가능).

**Building 1 직접 검증:**
- GT mesh 원본: 16.61m
- 우리 Stage 3 출력: 16.41m ← GT와 거의 일치
- GT_convex (잘못된 reference): 8.56m
→ Stage 3 알고리즘(convex polytope) 자체는 GT 비슷한 출력을 만듦. 알고리즘 교체 불필요.

---

## 15. Stage 3 개선 방향: G2 (Surface-level Grouping) + 통합 재설계

### 15.1 G1 → G2 전환의 4가지 근거

1. **thesis novelty:** "순차 파이프라인과의 차이"가 surface 단위에서만 성립. Patch 단위는 일반 normal smoothing과 차별화 안 됨.
2. **용어 일관성:** "평면 인스턴스 그룹", "대표 평면", "inter-primitive" 모두 surface 명시.
3. **Cycle 의미:** G2에서만 f_i 변경 → 다른 surface로 진짜 재할당. G1에선 voxel 위치로 결정되어 cycle 무의미.
4. **Stage 2-3 인터페이스:** G2 = Stage 3 surface와 같은 단위 → 자연스러운 통합.

현 G1은 implementation choice (학습 안정성 + 계산 효율). thesis 표현은 G2 의도 그대로.

### 15.2 G2 알고리즘 후보

| 후보 | 알고리즘 | 장점 | 단점 |
|------|---------|------|------|
| A. Voxel + spatial | (class, large voxel ~1m, dir bin) + post-merge by (n, plane_d) | voxel hash 효율 | 같은 wall의 cell split |
| B. Region growing | (class, n similarity, plane_d similarity, spatial connectivity) | surface 직접 표현 | 효율 (매 T iter) |
| C. Hybrid | (class, dir bin) + plane_d clustering + connected component | 단순 + 정확 | 구현 복잡도 |

Trade-off: 988K primitive에 매 T=500 iter 호출 → 1분 미만 필요. 학습 초기 noisy primitive → warmup 강화 필요 가능.

### 15.3 Stage 2→3 인터페이스 (G2 위에서)

Stage 2: 매 T iter G2 호출 → surface 단위 group_id. L_structure가 group별 rep_n/rep_d 향해 정렬. 학습 끝에 ckpt에 G2 group_id 저장.
Stage 3: ckpt의 G2 group_id 그대로 받음. Stage 3 자체 clustering 제거 또는 thin wrapper.

Baseline/Mutual: G2 grouping 학습 안 함. Stage 3 입구에서 post-hoc G2 호출.
Structure/Both: trained ckpt의 G2.
→ 4조건 모두 같은 grouping 알고리즘으로 평가 — fair comparison.

### 15.4 4조건 ablation 통합 의미

| Cond | Stage 2 학습 grouping | Stage 3 입력 | 측정하는 것 |
|------|---------------------|------------|---------|
| Baseline | 없음 | post-hoc G2 | grouping만의 효과 (control) |
| Mutual | 없음 | post-hoc G2 | + L_mutual 효과 |
| Structure | G2 (학습 중) | trained G2 | + L_structure 학습 시 효과 |
| Both | G2 (학습 중) | trained G2 | + 두 메커니즘 + 시너지 |

### 15.5 Cycle 재검증 (G2 위에서)

G2 위에서 §14.4의 4고리 재측정:
- 고리 1: L_normal_align gradient magnitude (C3a가 여전한지)
- 고리 3: f_i 변경 → surface 재할당 비율 (G1의 0.45% 대비 증가 기대)
- 고리 4: 그룹 변동률 (G1의 2% 대비 증가 기대)
- Both > Structure 시너지 발생 여부

### 15.6 알고리즘 교체 검토 결과 (유지: convex polytope)

Building 1 직접 검증에서 convex polytope 자체가 GT 비슷한 출력을 만듦 확인.
PolyFit, Plane arrangement 등 검토했으나 알고리즘 교체보다 grouping 정의(G2) + 인터페이스가 우선.

### 15.7 측정 인프라 정정 (병행)

| # | 문제 | 상태 |
|---|------|------|
| 1 | bbox_margin 자동화 | 정정 완료 |
| 2 | GT_convex 절반 축소 | 미완. GT direct 93.9% lower bound 채택 또는 cos_thresh 정정 |
| 3 | eval metric 가혹성 | 진단됨. multi-to-one matching 또는 area-weighted metric 도입 검토 |

---

## 16. C3 진단 결과 (확정, 3 component 분해)

### 16.1 C3a: Photo loss redundancy — 직접 입증

| 측정 | 값 | 해석 |
|------|-----|------|
| L_normal_align 활성화 시점 (step 20k) | 0.000222 | 활성화되자마자 이미 매우 작음 |
| 활성화 후 첫 50 step | 0.000222 → 0.000104 | 빠르게 감소 (할 일 거의 없음) |
| 학습 끝 (step 30k) | 0.0000115 | 20배 감소했으나 절대값 무의미 |
| L_normal_align peak vs L_mutual_vert peak | 0.000222 vs 0.0326 | **L_structure가 L_mutual보다 135배 작음** |
| eval/normal_cos | step 2k: 0.929 → step 30k: 0.984 | photo loss만으로 normal 거의 완벽 정렬 |

### 16.2 인과 메커니즘
Photo loss(L_photo) + L_normal이 step 0~20k 동안 n_i를 이미 정렬 (normal_cos 0.984).
L_normal_align이 step 20k에 활성화될 때 그룹 내 normal 분산이 이미 매우 작음.
L_normal_align이 추가로 줄일 거리가 거의 없음 → σ_normal_intra +1% (Phase 2 효과 부재)의 근본 원인.

Phase 1(MatrixCity, PSNR 22, normal_cos 더 낮음)에서는 L_normal이 약해서 L_normal_align이 추가 정렬 여지가 있었음 → σ_normal_intra -45%.

### 16.3 L_coplanar도 유사
L_coplanar max magnitude: 7.5e-5. L_normal_align과 비슷한 수준으로 redundant 가능성.
다만 σ_coplanar은 -2~-9% 개선이 관측됨 — 작지만 0은 아님.

### 16.4 시너지 미입증의 근본 원인 확정
시너지 기대 경로: 메커니즘 2가 n_i 정렬 → 메커니즘 1이 정렬된 n_i로 f_i 교정 → 순환.
순환의 첫 고리: L_normal_align이 n_i를 이동시켜야 함.
첫 고리가 끊김: L_normal_align의 gradient가 L_mutual의 1/135 → n_i를 effective하게 이동 못함.
→ 메커니즘 1이 "메커니즘 2에 의해 정렬된 n_i"를 볼 수 없음 → 순환 불발 → 시너지 없음.

### 16.5 Thesis 함의 (G2 전환 반영)

**Negative result도 contribution:**
"어떤 환경에서 어떤 메커니즘이 작동하는지"의 boundary를 정량적으로 그어줌.

- 메커니즘 1 (L_mutual): strong/weak supervision 모두에서 작동 (Wall vert 개선 일관)
- 메커니즘 2 (L_structure with G1): strong supervision에서 redundant (C3a + C3b + C3c)
- 메커니즘 2 (L_structure with G2): C3b(patch unit) 해소, C3c(cycle) 해소 가능. C3a는 남음.
- 시너지: G1에서 미발현. G2에서 고리 3,4 복원 → 시너지 가능. Phase 3에서 고리 1도 복원 가능.

**G2 위에서의 시나리오:**
- G2 + Phase 2 합성: C3a가 남아 L_normal_align absolute magnitude 여전히 작을 수 있으나, across-patch 정렬(C3b 해소)로 Stage 3 품질 개선 가능.
- G2 + Phase 3 실데이터: C3a도 해소 → L_normal_align이 진짜 효과 + 시너지 가능.

**스케치 서술 방향:**
"G1(patch 단위)에서는 L_normal_align이 intra-patch smoothing에 그쳤으나, G2(surface 단위)에서는 across-patch 정렬이 가능. 합성 clean 환경에서는 photo redundancy(C3a)로 marginal contribution이 축소되며, 실데이터에서 효과 복원이 기대된다."

---

## 17. Measurement Infrastructure Fragility

### 17.1 발견된 측정 오류
**Bug 1 (bbox_margin, 정정 완료):** plane_intersection.py의 bbox_margin 고정 1.0m → flat 건물에서 QHull 실패 → 14건물 처리 실패. max(5.0, 0.5×extent)로 자동화 후 전체 수치 +10~17%p.

**Bug 2 (GT_convex 축소, 정정 미완):** gt_stage3_test.py에서 GT를 convex 통과시켰을 때 88% 건물이 절반 높이로 축소. 96.2% "천장"은 축소된 GT의 통과율이지 알고리즘 천장이 아님.

### 17.2 교훈
1. 모든 Stage 3 측정에 GT sanity check 포함: GT direct val3dity(93.9%), 건물 높이 비교
2. 코드 수정 시 regression test: 알려진 건물(bid=1,2,6,21,22)의 수치 변화 확인
3. Metric의 face count mismatch 한계 명시: pred ~7면 vs GT ~22면에서 sem accuracy, face IoU 과소 측정

### 17.3 Eval metric 가혹성
| Metric | vs scene.obj GT (~22 face/bldg) | vs GT_convex (~7 face/bldg) |
|---|---|---|
| sem accuracy | 21.6% | 46.1% |
| face IoU | 0.214 | 0.154 ↓ |
sem acc 21→46%: greedy 1-to-1 matching에서 face count mismatch 시 GT face 64%가 unmatched → 과소 측정.
논문 보고: matched subset metric 병행, face count mismatch 한계 명시.