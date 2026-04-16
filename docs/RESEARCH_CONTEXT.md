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
f_i: 직접 gradient 없음(그룹 할당 미분 불가). 메커니즘 1이 f_i 교정 담당.

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
| Depth MAE | mean(\|D_render-D_GT\|) | 2DGS |
| Normal cos | mean(n_render·n_GT) | 2DGS |
| Wall 수직도 | wall 중 \|n·e_g\|<sin(10°) 비율 | 본 연구 |
| mIoU | mean(TP/(TP+FP+FN)) | AlignGS |
| PSNR | -10·log10(MSE) | 3DGS |
| val3dity | Ledoux(2019) | PLANES4LOD2 |
| 면 IoU | 생성 vs GT | Point2Building |
| Hausdorff | 최대 거리 | City3D |
| σ_normal_intra | 그룹 내 법선 분산 | 본 연구 |
| σ_coplanar | 그룹 내 coplanarity 오차 | 본 연구 |

---

## 7. 실험 조건

### Ablation
Baseline / Joint(+L_mutual) / Joint+Structure(+L_mutual+L_structure).
조건부: Joint-GTOnly, Joint-Weak.

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
