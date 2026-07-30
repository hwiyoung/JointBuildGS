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

### 1.4 연구 목표와 기여

본 연구의 목표는 영상 기반 2DGS primitive를 기하-의미론적으로 공동 최적화하고, 그 결과를 CityGML LOD2 수준의 구조적 건물 모델로 읽어내는 것이다.

**기여 1 — 기하-의미론 공동 최적화 프레임워크.**
2DGS primitive에 depth, normal, semantic, photo supervision을 결합하고, 건물 도메인 규칙과 구조 정렬 손실을 추가하여 wall / roof / terrain evidence를 학습한다.

**기여 2 — Intra-primitive domain-rule loss (L_mutual).**
L_mutual은 wall normal의 gravity 정합성, roof/wall/terrain semantic-geometric consistency, height relation을 primitive level에서 부과한다. 실험적으로 Mutual은 wall verticality를 크게 개선하며 (Phase 2-2 wall vert frac 28.0%→79.3%), 이는 Stage 3 footprint/read-out evidence의 품질을 높이는 핵심 신호이다.

**기여 3 — Surface evidence-to-CityGML read-out.**
Stage 2의 joint-optimized evidence를 Roofer-style 2.5D roof-partition read-out으로 변환하여 RoofSurface, WallSurface, GroundSurface를 갖는 CityJSON / CityGML semantic shell을 생성한다. 기존 Roofer/3DBAG와 달리, 외부 roofprint를 입력으로 사용하지 않고 wall-derived footprint와 roof evidence relation으로 building shell을 구성한다. 최종 end-to-end 설정에서는 외부 roofprint / footprint를 입력으로 사용하지 않는다. 다만 read-out module과 Stage 2 evidence 품질을 분리 검증하기 위해 GT-derived per-building sanity와 GT oracle split diagnostic을 별도로 수행한다.

**기여 4 — Failure mode analysis of generic plane assembly.**
Convex polytope와 PolyFit-style generic plane assembly가 local surface evidence에서 valid-small solid, coverage collapse, non-manifold error를 만들 수 있음을 정량적으로 분석한다 (P1-3b convex polytope 4 condition ablation, PolyFit Phase 2 GT input 40% val3dity, Phase 0c backend two-bug analysis). CityGML LOD2 read-out에는 semantic relation-based roof-partition 구조가 더 적합함을 P1-4a Part B에서 보인다 (simple/medium 4건 coverage 90-100%).

### 1.5 메커니즘 1과 2의 관계 (G1 cycle 약화 정정)

이전 thesis sketch는 "메커니즘 1과 2의 순환 효과(cycle of feedback)"를 핵심 contribution으로 주장했으나, P1-3b cycle 검증 결과 G1 위에서 cycle 4고리(L_structure 강도, n_i→f_i 교정, f_i 재할당, 그룹 변동)가 모두 약하게 나타났다 (§14.4). 이는 두 가지 원인에서 비롯한다:

1. **C3a (photo redundancy):** Photo loss + L_normal이 이미 n_i를 정렬 (normal_cos 0.984) → L_normal_align의 marginal contribution 매우 작음 (L_mutual의 1/135).
2. **C3b (G1 patch unit):** G1의 5cm voxel hash가 patch 단위 → L_normal_align이 intra-patch smoothing에 그침.

따라서 본 논문은 "cycle of feedback"이 아니라 **두 메커니즘의 독립 효과 + 결합 효과 + 조건적 시너지**를 평가한다. Phase 3 실데이터(L_normal 약화) 또는 G2(surface-unit grouping) 환경에서 cycle 일부 복원 가능성은 별도로 검증한다.

---

## 2. 파이프라인

### Stage 1: SfM/MVS + 2D Segmentation
- COLMAP SfM/MVS → 카메라 포즈, 포인트 클라우드, D_MVS, n_MVS
- Grounded SAM 2 → 2D segmentation GT (K=4)
- Gravity: terrain MVS 법선 평균 = UP → e_g = -UP. 학습 전 1회.

### Stage 2: 구조 인식 공동 최적화
- gsplat/2DGS + L_mutual(intra) + L_structure(inter)

### Stage 3: Evidence-to-CityGML read-out

#### Stage 3의 역할

Stage 3는 Stage 2에서 학습된 2DGS primitive evidence를 CityGML LOD2 semantic shell로 변환하는 read-out module이다. Stage 3의 목적은 새로운 generic polygon reconstruction backend를 제안하는 것이 아니라, Stage 2의 joint geometric-semantic optimization이 생성한 wall / roof / terrain evidence를 구조적 건물 모델로 읽어내는 것이다.

#### Stage 3 입력 evidence

Stage 2 checkpoint에서 다음 evidence를 export한다.

- primitive centers `c_i`
- primitive normals `n_i`
- in-plane scales `s_i`
- opacity
- semantic logits / probabilities `f_i`
- class probabilities: Roof, Wall, Terrain
- support area proxy
- optional rendered depth / normal / semantic evidence

이 evidence는 CityJSON이 아니며, PLY / NPZ / custom JSON 형태로 저장한다. CityJSON은 최종 building shell에만 사용한다.

#### Stage 3 처리 흐름

```
Stage 2 checkpoint
  ↓
Primitive evidence export (c_i, n_i, s_i, opacity_i, f_i)
  ↓
Building evidence partition
  - GT bid for sanity (E1, E3)
  - automatic split for full scene (E2, E4)
  ↓
Wall-derived footprint / roofprint estimation
  ↓
Roof evidence projection and roof partition
  ↓
Semantic shell assembly (RoofSurface / WallSurface / GroundSurface)
  ↓
CityJSON / CityGML export
  ↓
Validation
  val3dity + height + recall/precision/F + vol_ratio + Hausdorff
```

세부 단계:

1. **Evidence export:** evidence_primitives.npz, evidence_primitives.ply
2. **Building evidence partition:** GT bid (sanity) 또는 automatic split (full scene)
3. **Wall-derived footprint estimation:** wall evidence ground-plane projection, wall direction modes / support lines / boundary graph
4. **Roof partition:** roof evidence를 footprint domain에 projection, roof plane candidates / normal modes / height relation. Archetype label은 optional diagnostic.
5. **Semantic shell assembly:** RoofSurface / WallSurface / GroundSurface, closed shell
6. **CityJSON / CityGML export**
7. **Validation:** val3dity (formal), h_err, recall coverage, pred-to-GT precision, F-score, vol_ratio, footprint IoU, Hausdorff / Chamfer, stepwise failure reason

#### Roofer / 3DBAG와의 관계

Roofer/3DBAG는 classified point cloud와 2D roofprint polygon을 입력으로 LoD2 building model을 생성하는 대표적인 building-prior 기반 reconstruction pipeline이다. Roofer는 roofprint domain에서 roof partition을 만들고, vertical wall과 roof planes를 조합해 2.5D model을 생성한다. 본 연구의 Stage 3는 이러한 Roofer-style roof-partition read-out과 구조적으로 유사하지만, 중요한 차이가 있다. Roofer는 외부 roofprint polygon을 입력으로 사용하지만, 본 연구는 Stage 2에서 학습된 wall / roof / terrain evidence에서 building partition과 footprint / roofprint를 추정한다. 따라서 본 연구의 핵심 비교는 "roofprint가 주어진 point-cloud reconstruction"이 아니라, "joint-optimized image-derived evidence가 CityGML read-out에 충분한가"이다.

#### 기존 backend 결과의 지위 (diagnostic baseline)

Convex polytope와 PolyFit-style generic plane assembly는 diagnostic baseline으로 유지한다. 두 방법은 local surface candidate를 global support surface로 조립하는 과정에서 valid-small solid, coverage collapse, non-manifold error를 보였다.

- **Convex polytope (P1-3b 4 condition ablation):** GT input val3dity 96.2%, v4 input 32.1%. Height/coverage collapse 일관 (B1 4.22m vs GT 16.61m, B21 3.15m vs 17.42m). Support-plane d-assignment + orientation fix 시도해도 coverage 회복 실패.
- **PolyFit (CGAL+SCIP+repair recipe, Phase 2):** GT input 40% val3dity. flat 3/3 정확 재구성 (vol_ratio=1.00, h_err=0.00m). hip/complex/tri-slope 두 모드 실패: 303 non-manifold 잔존 또는 val3dity ✓ but coverage <10% (MIP minimal valid 선호). 66+ planes에서 CGAL assertion failure.
- **2.5D extrusion (legacy, port from PlanarSplatting ref):** val3dity 67.2% pass, quality (h_err/coverage/Hausdorff) 미측정. flat 100% pass, complex 34.5% pass.

→ 최종 Stage 3 본류는 Roofer-style relation-based read-out으로 전환.

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

**메커니즘 1과의 동시 작용 (G1 cycle 약화는 §1.5 / §14 참조):**
매 iteration에서 n_i에 대한 gradient:
∂L/∂n_i = ... + ∂L_mutual/∂n_i + ∂L_normal_align/∂n_i
하나의 파라미터에 도메인 규칙("벽이니까 수평") + 면 단위 정렬("같은 면이니까 같은 방향")이 동시 작용. 단, G1(patch 단위) 위에서는 두 효과의 독립 결합으로 평가 (cycle 약함).

**s_i에 별도 제약 없음.** Stage 3 Roofer-style read-out에서 footprint는 wall evidence 위치/normal에서 추정되므로 s_i에 의존하지 않음.

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

### Stage 2 평가
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

### Stage 3 평가 (Roofer-style read-out)
| 지표 | 정의 | 레퍼런스 |
|------|------|---------|
| val3dity | formal CityJSON validity | Ledoux(2019) |
| h_err | \|output_h - GT_h\| | 본 연구 |
| recall coverage | GT surface samples within 0.5m of pred mesh | 본 연구 |
| pred-to-GT precision | predicted samples within 0.5m of GT mesh | 본 연구 |
| F-score | precision/recall harmonic mean | Point2Building |
| vol_ratio | output_vol / GT_vol | 본 연구 |
| footprint IoU | predicted footprint vs GT footprint | City3D |
| Hausdorff / Chamfer | mesh-to-mesh distance | City3D, AGS |
| edge incidence | manifoldness, open edges, non-manifold edges | val3dity |
| failure_reason | EVIDENCE_INSUFFICIENT, FOOTPRINT_FAIL, ROOF_PARTITION_FAIL, SHELL_ASSEMBLY_FAIL, VAL3DITY_FAIL, LOW_PRECISION_OVERFILL, LOW_RECALL_UNDERFILL, COMPLEX_MULTIPART, SHARED_WALL_LIKELY | 본 연구 |

### Instance-level (E2, E4 자동 split)
| 지표 | 정의 |
|------|------|
| instance precision | predicted components matched to GT / total predicted |
| instance recall | matched GT / total GT |
| over-merge / over-split count | one-to-many / many-to-one matching |
| component-to-GT IoU | bbox 또는 footprint IoU |

### 4조건 ablation (E3, E4)
| 조건 | 구성 | 검증 |
|------|------|------|
| Baseline | L_photo+L_depth+L_normal+L_nc+L_sem | 메커니즘 없음 |
| Mutual only | +L_mutual | 메커니즘 1 단독(intra) |
| Structure only | +L_structure | 메커니즘 2 단독(inter) |
| Both | +L_mutual+L_structure | 동시 작용 + 결합 |

---

## 7. 데이터

### 성수동 (Phase 3 실데이터)
180장 oblique (DJI, 70m, GSD~1cm). COLMAP 100장. data/seongsu/.

### 3D BAG (Phase 2 합성)
LOD2.2. Amsterdam Jordaan 131건물. data/3dbag/.

### MatrixCity (Phase 1 학습 검증)
Small City Aerial, 5,621장 (CityGSV2 COLMAP sparse).

### GauU-Scene (Phase 3 서브)
Real UAV.

---

## 8. 용어 규칙

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
| evidence-to-CityGML read-out | convex polytope / plane intersection 기반 변환 |
| Roofer-style 2.5D roof-partition | generic plane assembly |
| 두 메커니즘의 결합 효과 | 메커니즘 1과 2의 순환 효과 |

---

## 9. 레퍼런스

### 건물 구조 추출
- PolyFit (Nan & Wonka, 2017), City3D (Huang et al., 2022), KSR (2020), Point2Building (2024), 3DBAG, PLANES4LOD2 (2024), SAT2BUILDING (2025)
- Roofer (3DBAG / TU Delft) — 본 연구 Stage 3 reference

### 미분 가능 렌더링
- 3DGS (Kerbl et al., 2023), 2DGS (Huang et al., 2024), PGSR (2024), PlanarSplatting (2025), gsplat

### 항공/도시
- AGS (Wu et al., 2024), ULSR-GS (Li et al., 2025), CityGaussianV2

### Building-prior + GS
- GS4Buildings (Zhang et al., 2025): LoD2 → GS prior. 본 연구와 반대 방향.
- Gaussian Building Mesh (Gao et al., 2025): GS → building mesh, structured 변환 미포함.

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

## 10. 예비 실험 (PlanarSplatting, 외부 동결 자료)

이 절의 원본은 현재 repository root가 아니라
`artifacts/manifests/transitional_quarantine_legacy_external_20260730.yaml`이 해석하는
sibling artifact quarantine에 보존되어 있다. 아래 수치와 연구 해석은 이동 전 기록을 그대로 유지한다.

### L_mutual 효과 (Synthetic B)
Clean wall normal 8.9°→3.8°, Noisy 9.0°→4.3°. 밀착 실패(coverage 6-26%) → gsplat 변경 근거.

### 법선 지배성 (Synthetic A)
법선 20° → val3dity -53%p. 분류 30% → -10%p. 2위의 5배.

### 성수동
mIoU=0.81. L_mutual gravity 미보정 보류. Stage 3: 11 instance, non-watertight.

---

## 11. gsplat 2DGS 구현 주의사항

실제 구현 중 발견한 gsplat 1.4.0 + 2DGS 관련 함정. Claude Code 참조용.

### 11.1 Densification gradient key
gsplat 2DGS는 gradient를 `gradient_2dgs` 키로 전달하지만, DefaultStrategy의 `key_for_gradient` 기본값은 `"means2d"`. 기본값 사용 시 grow가 0회 실행되어 프리미티브가 prune만 됨.
**수정:** `DefaultStrategy(..., key_for_gradient="gradient_2dgs")` 명시.

### 11.2 Scales shape
`rasterization_2dgs`는 scales를 (N,3)으로 요구 (dim2 ≈ 0으로 설정). (N,2)로 전달 시 오류.

### 11.3 Distortion loss weight
Depth distortion loss의 weight가 과도하면 total loss를 지배함. 초기값으로 w_distort=100은 문제. 0 또는 낮은 값으로 시작 후 조정.

### 11.4 L_nc 구현
gsplat의 `render_normals_from_depth`는 shape 불일치 이슈 있음. 자체 구현 권장:
- `depth_to_normal(D_render)`: 인접 픽셀 finite difference → cross product
- n_render는 gsplat이 world-frame으로 변환해서 반환 (추가 변환 불필요)

### 11.5 Densification sync
gsplat strategy가 params dict를 교체해도 우리 model의 파라미터에 자동 반영 안 됨.
**수정:** `_sync_params_to_model()` 호출로 명시적 동기화.

### 11.6 Render normals 좌표계
`render_normals`는 이미 world-frame. `render_normals_from_depth`와 비교 시 좌표계 일치 확인.

---

## 12. Phase 1 Smoke Test 결과 (2026-04-16)

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

### 이전 시도 (실패)
성수동 30k, eval PSNR 16.3 dB, N 62k. gradient_2dgs 버그로 grow 미작동이 원인.

---

## 13. Phase 2-2 Stage 2 학습 결과 (2026-04-25)

### 13.1 Stage 2 4조건 결과
| 조건 | PSNR | Wall vert | σ_normal_intra | σ_coplanar |
|------|------|----------|---------------|-----------|
| Baseline | 40.35 | 28.0% | 14.74° | 1.91m |
| Mutual | 40.93 | **79.3%** | 12.63° | 1.84m |
| Structure | 40.96 | 28.4% | 14.88° | 1.86m |
| Both | 39.81 | **79.4%** | 12.99° | 2.01m |

→ L_mutual은 wall verticality에서 강한 효과 (28% → 79%). L_structure는 σ_normal/σ_coplanar에서 marginal 효과만. 상세 분석은 §14 (cycle 검증).

### 13.2 v4-mode wall clustering (Stage 3 backend audit의 일환)
Mutual 조건에서 wall over-merge 해결 (P1-2 4/5 GO). Mode-based azimuth detection으로 적도 chaining(v3 DBSCAN의 한계) 우회.
단, 이는 Stage 3 backend audit의 한 단계이며, 최종 Stage 3 본류는 §2 Roofer-style read-out으로 전환.

---

## 14. Cycle 검증 결과 (G1 위에서) — thesis "cycle of feedback" 정정

### 14.1 Cycle 4고리 측정

| 고리 | 검증 방법 | 결과 |
|------|---------|------|
| 1. L_structure → n_i 정렬 | Loss magnitude | L_structure : L_mutual = **1 : 135** → 약함 |
| 2. 정렬된 n_i → f_i 교정 | L_mutual 수식 분석 | (n·e_g)² 작아질수록 ∂L_mut/∂f_i 작아짐 → **정렬되면 교정 비활성화** |
| 3. f_i 변경 → 그룹 재할당 | f_i argmax change | step 25k→30k Structure 0.45%, Both 0.29% → **trigger 없음** |
| 4. 그룹 변동 | n_groups 통계 | CV 2.01%, consecutive change 0.007% → **거의 정적** |

→ G1 위에서 thesis "동시작용 cycle"이 4고리 모두 약함.

### 14.2 근본 원인 3가지

**C3a (photo redundancy):** Photo loss + L_normal이 step 0~20k 동안 n_i를 이미 정렬 (normal_cos 0.984). L_normal_align(step 20k 활성화)이 추가로 줄일 거리 거의 없음. L_normal_align peak vs L_mutual peak: 0.000222 vs 0.0326 (1/135).

**C3b (G1 patch unit):** G1의 5cm voxel hash + 12 dir bin이 patch 단위 → L_normal_align이 intra-patch smoothing에 그침. Across-patch/surface 단위 corner tilt 등 못 잡음.

**C3c (G1 grouping이 위치 기반):** f_i 변경이 voxel hash에 영향 안 줌 → 고리 3,4 끊김.

### 14.3 Perturbation test로 본 C3a 정밀화

| Shift | Phase 1 ΔdB | Phase 2 ΔdB | 비율 |
|---|---|---|---|
| 0.10m | -6.45 | -0.85 | 7.6× |
| 0.50m | -7.83 | -5.00 | 1.6× |
| 1.00m | -7.81 | -7.50 | 1.04× |

C3a(photo redundancy)는 sub-meter(cm-dm) 영역에 한정. 1m 이상은 대칭. → Phase 3 실데이터(L_normal 약화)에서 C3a 일부 해소 가능성.

### 14.4 thesis 함의

**G1 위에서 "cycle of feedback" 미입증.** 두 가지 contribution claim:

- **Negative result도 contribution:** "어떤 환경에서 어떤 메커니즘이 작동하는지"의 boundary를 정량적으로 그어줌.
  - 메커니즘 1 (L_mutual): strong/weak supervision 모두에서 작동 (Wall vert 28% → 79%).
  - 메커니즘 2 (L_structure with G1): strong supervision에서 redundant.
  - 시너지: G1에서 미발현. Phase 3에서 고리 1 복원 가능.

- **G2 (surface-unit grouping) 가능성:** C3b/C3c는 G2로 해소 가능 (f_i가 grouping 조건 → 고리 3,4 복원). C3a는 G2로도 해소 안 됨. **단, G2 재학습은 본 thesis scope 밖**. Phase 3 future work로 명시.

**스케치 표현:**
"G1(patch 단위)에서는 L_normal_align이 intra-patch smoothing에 그치며, photo redundancy(C3a)로 marginal contribution이 축소된다. 두 메커니즘은 결합 시너지가 아닌 독립 효과로 평가하며, Phase 3 실데이터에서 photo supervision 약화 시 효과 복원이 기대된다."

---

## 15. Stage 3 backend audit 결과 (P1-3 ~ P1-3b)

### 15.1 Audit 동기

Phase 2-2 Stage 2 학습은 양호 (mIoU 0.97, F1@0.5m 0.97, G1 σ_coplanar 2.6mm). 그러나 초기 Stage 3 (convex polytope 기반)에서 height/coverage collapse 발견. 4가지 backend candidate audit 수행.

### 15.2 Backend별 결과

| Backend | GT input | v4 input | quality 측정 | 결론 |
|---------|----------|----------|------------|------|
| Convex polytope | val3dity 96.2% | 32.1% | h_err/coverage/vol_ratio 측정 | Height/coverage collapse, support fix 시도 후에도 회복 안 됨. P1-3b NG |
| PolyFit (CGAL+SCIP+repair recipe) | 40% val3dity | partial | 측정 | Flat 정확 재구성, hip/complex valid-small 또는 over-segment |
| 2.5D extrusion (legacy port) | 67.2% val3dity | 미측정 | 미측정 | Flat 100%, complex 34.5%. quality 검증 미완 |
| RANSAC | spot-check | 미측정 | 미측정 | 2/5 |

### 15.3 Phase 0c backend two-bug analysis

Convex polytope 자체에 두 backend 버그 분리:
1. **S4 polygon planarity bug:** `_merge_coplanar_triangles` 이후 face polygon이 assigned plane으로부터 max 44.4mm 벗어남 → val3dity 203 발생.
2. **d=centroid bug:** `_gt_envelope_planes`가 `d = n · centroid` 사용 → wall jog/alcove에서 inner sub-face가 polytope를 안쪽으로 자름 → vol_ratio collapse (B0: GT input vol_ratio 0.058).

### 15.4 PolyFit Phase 2 detailed

GT input 9건 결과:
- Flat 3/3 ✓ (B1: vol_ratio 1.00, B4: 1.00, B2: 0.05 small but valid)
- Hip 0/3, tri-slope 0/1, complex 0/1
- val3dity ✓ but coverage <10% pattern: B2 (cov 2.4%), B8 gable (cov 5.7%), B6 hip Stage B (cov 0.5%)
- bid 3 (66 planes) CGAL assertion failure

→ "val3dity 통과해도 quality 부족" 패턴 정량 검증. PolyFit-style hypothesis-and-selection이 본 building distribution에 부적합.

### 15.5 Audit의 thesis 자산화

이 audit 결과는 **기여 4 (Failure mode analysis of generic plane assembly)**의 정량 근거가 된다. "Convex polytope, PolyFit-style이 local surface evidence를 global support로 조립하는 과정에서 valid-small solid, coverage collapse, non-manifold error를 만드는 실패 모드를 정량적으로 분석한다."

---

## 16. P1-4a Part B — Roofer-style read-out feasibility

### 16.1 결과 (6건 GT-derived per-building relation read-out)

| bid | type | h_err | coverage | edge_ok | val3dity |
|-----|------|-------|----------|---------|----------|
| B1 | flat | 0.00m | **99.0%** | ✓ | NOT_RUN |
| B2 | flat | 0.00m | **100.0%** | ✓ | NOT_RUN |
| B8 | gable | 0.00m | **98.8%** | ✓ | NOT_RUN |
| B0 | tri-slope | 0.00m | **90.2%** | ✓ | NOT_RUN |
| B6 | hip | 3.61m | 88.3% | ✓ | NOT_RUN |
| B3 | complex | 7.31m | 36.5% | ✓ | NOT_RUN |

Simple/medium 4건 (B1, B2, B8, B0): coverage 90-100%, h_err 0.00m. 이전 backend (convex polytope, PolyFit) 대비 압도적 quality.
hip 1건 (B6): partial GO. complex 1건 (B3): NG.

### 16.2 의미

P1-4a Part B는 4 backend audit에서 처음으로 GT input에서 정량 quality (h_err < 1m AND coverage > 50%)를 달성한 backend다. Roofer-style relation-based read-out이 본 thesis Stage 3 본류로 적합한 첫 정량 근거.

단, val3dity NOT_RUN (validator missing) → E0에서 formal pass/fail 확인 필요.

---

## 17. Measurement Infrastructure Fragility

### 17.1 발견된 측정 오류

**Bug 1 (bbox_margin, 정정 완료):** plane_intersection.py의 bbox_margin 고정 1.0m → flat 건물에서 QHull 실패 → 14건물 처리 실패. max(5.0, 0.5×extent)로 자동화.

**Bug 2 (GT_convex 절반 축소, P1-3a Phase 0a에서 정정):** ratio_3D 계산이 vertex mean을 face centroid로 사용 → B2 ratio_3D=1.949 (정의상 불가능). Fan triangulation + signed tetrahedra로 정정. B6 NON_CONVEX 판정 무효 (재계산 후 ratio_3D=0.859 → CONVEX_OK).

**Bug 3 (gravity 축, Phase 0d에서 발견):** 이전 측정에서 up=[0,0,1], 실제 gravity=[0,1,0] (Y-down). 90° 어긋남. 올바른 측정 후 wall vert frac 5-8% → 87.8% (Mutual). "primitive n_i 부정확" 진단은 무효.

### 17.2 교훈

1. 모든 Stage 3 측정에 GT sanity check 포함: GT direct val3dity, 건물 높이 비교, ratio_3D ≤ 1 검증.
2. 코드 수정 시 regression test: 알려진 건물(bid=1,2,6,21,22)의 수치 변화 확인.
3. 좌표계/축 확인을 모든 측정의 첫 단계로. gravity 하드코딩 금지, GT terrain normal에서 검증.
4. val3dity ≠ quality. coverage/h_err/Hausdorff 함께 측정해야 정량 평가 가능.

### 17.3 Eval metric 가혹성

| Metric | vs scene.obj GT (~22 face/bldg) | vs GT_convex (~7 face/bldg) |
|---|---|---|
| sem accuracy | 21.6% | 46.1% |
| face IoU | 0.214 | 0.154 ↓ |

Greedy 1-to-1 matching에서 face count mismatch 시 GT face 64%가 unmatched → 과소 측정.
논문 보고: matched subset metric 병행, face count mismatch 한계 명시.

---

## 18. 실험 단계 요약

상세 프롬프트는 EXPERIMENT_PLAN.md.

| 실험 | 입력 evidence | building split | 목적 | 제안 방법 성능 주장 |
|------|-------------|--------------|------|--------------------|
| E0 | (P1-4a Part B 결과) | (재실행 아님) | val3dity preflight + precision metric | 아니오 |
| E1 | GT-derived | GT bid | read-out sanity / 131건물 일반화 | 아니오 |
| E2 | GT-derived | automatic | clean evidence에서 building split 검증 | 아니오 |
| E3 | Stage2-derived | GT oracle | Stage2 evidence 품질 upper-bound, 4조건 | 부분적 진단 |
| E4 | Stage2-derived | automatic | end-to-end Stage 3, 4조건 | 예 |

---

## 19. 비교 실험 계획

(a) 영상+순차+footprint, (b) 영상+순차-footprint, (c) 제안, (d) LiDAR upper bound.

상세 비교 protocol은 Phase 3 단계에서 EXPERIMENT_PLAN.md에 추가.

---

## 20. Synthetic 실험

### Synthetic A (완료)
법선 지배성: 20°→val3dity -53%p, 분류 30%→-10%p. 2위의 5배.

### Synthetic B (Phase 2)
이상적+clean 기본. 노이즈: depth/seg. 카메라: 이상적/oblique/nadir/뷰 감소.
