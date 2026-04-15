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
안전장치: L_sem이 독립적으로 f_i를 GT 방향으로 강제. L_mutual만 단독이면 p_c→0 trivial solution 위험.

Gradient: n_i, f_i 양방향. c_i(L_height 높이만). s_i 없음.
Warmup: 0~N/3에서 λ_m=0.

### L_structure (메커니즘 2, Inter-primitive)
매 T iter 그룹핑 (class + 법선 cos>th + 공간 근접). 대표 평면 Π_k = (n_k, d_k) 가중 평균.

L_normal_align = Σ_k Σ_{i∈G_k} (1-n_i·n_k)². n_i gradient, n_k detach.
L_coplanar = Σ_k Σ_{i∈G_k} (n_k·c_i+d_k)². c_i gradient, n_k/d_k detach.
L_structure = λ_na·L_normal_align + λ_cp·L_coplanar.

L_coverage(s_i): 후보. densification 대비 검증.
f_i: 직접 gradient 없음(그룹 할당 미분 불가). 메커니즘 1이 f_i 교정 담당.
한계: 오분류 프리미티브가 잘못된 그룹에 편입될 수 있음. 메커니즘 1의 f_i 교정이 선행되어야 하므로 warmup 순서(L_mutual → L_structure)가 필수.

대표 법선 정확도 위험 → 안전장치: warmup(2N/3 이후), 재계산, 가중 평균.
Warmup: 2N/3 이후 활성화 (비율 기반, §5 참조).

---

## 5. 학습 전략

### Warmup (비율 기반)
모든 warmup은 총 iteration N에 대한 비율로 정의. N이 달라져도 학습 단계의 의미가 보존됨.

| 구간 | Iteration | 활성 손실 |
|------|----------|----------|
| 초기 | 0 ~ N/3 | L_depth+L_normal+L_nc+L_sem+L_photo |
| 중기 | N/3 ~ 2N/3 | +L_mutual |
| 후기 | 2N/3 ~ N | +L_structure |

### 하이퍼파라미터 (초기값)
| 파라미터 | 값 | 비고 |
|---------|-----|------|
| λ_nc | 0.01 | 2DGS 참고 |
| λ_s | 0.1 | 예비 실험 |
| λ_p | 1.0 | 표준 |
| λ_m | 0.1 | warmup(N/3) 후 |
| λ_na | TBD | 실험적 |
| λ_cp | TBD | 실험적 |
| τ (L_slope) | 0.15 | 예비 실험 |
| T (그룹 주기) | 500 | 실험적 |
| N (총 iter) | 30000 | 3DGS/2DGS 관례 (공정 비교) |

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
