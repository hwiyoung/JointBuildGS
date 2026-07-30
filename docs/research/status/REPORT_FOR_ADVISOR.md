---
title: 학위논문 진행 상황 보고
subtitle: 도시 규모 건물의 구조적 3D 복원을 위한 기하-의미론 공동 최적화
author: 김휘영
date: 2026-04-26
---

# 학위논문 진행 상황 보고

**연구 주제**: 도시 규모 건물의 구조적 3D 복원을 위한 기하-의미론 공동 최적화

**보고일**: 2026-04-26

**현재 단계**: Phase 2 (3D BAG 합성) 진행 중

---

## 0. Executive Summary

**연구 한 줄**: 미분 가능 렌더링 기반 평면 프리미티브 (gsplat + 2DGS) 위에 두 수준의 공동 최적화 — *intra-primitive 도메인 규칙* (L_mutual) + *inter-primitive 구조 정합* (L_structure) — 를 통합하여 LOD2 CityGML 품질 향상을 검증하는 박사 연구.

**현재 위치**:
- Phase 1 (MatrixCity, *primitive 수준 검증*): **완료, 6/6 통과**
- Phase 2 (3D BAG 합성, *CityGML 수준 평가*): **진행 중**, Stage 2 학습 4 조건 완료, Stage 3 변환 + ablation 측정 수행, **측정 인프라 신뢰성 문제 두 건 발견 → 결론 보류**
- Phase 3 (real UAV + 성수동): 미착수

**핵심 진행 (긍정)**:
1. **메커니즘 1, 2 가 primitive 수준에서 의도대로 작동 — Phase 1, 2 양쪽에서 일관 검증.** Wall 수직화 (16.9% → 88.3%, Phase 1; 28% → 79%, Phase 2), σ_normal 감소 (Phase 1 −45%).
2. **Stage 3 (CityGML) 4 조건 ablation 실측 완료**. val3dity 통과율 Baseline 52.7% / Mutual 48.9% / Structure 55.0% / Both 54.2% (post-fix). Structure 가 일관 최상위.
3. **Phase 1 Both 조건이 두 메커니즘 효과를 동시 보존** — Phase 2 CityGML 평가 입력 적합성 확인.

**핵심 한계 (솔직)**:
1. **Stage 3 측정 인프라의 fragility 발견**: (a) `bbox_margin` 1 줄 버그로 v3 측정값 +10~20%p 왜곡, (b) GT_convex 기준점이 GT 의 약 절반 높이로 systematic 축소 — 88% 건물에서 발생. 따라서 **"Stage 3 알고리즘 천장" 의 진짜 값 미정** 상태이며, 4 조건 결과의 *상대 비교* 만 신뢰 가능.
2. **Stage 2 ↔ Stage 3 인터페이스 단절 발견** (C2): L_structure 가 학습 중 만든 group 정보가 Stage 3 의 자체 grouping (다른 알고리즘) 에 전달되지 않음. 메커니즘 2 의 효과가 Stage 3 측정에서 부분적으로만 드러남.
3. **L_normal_align 의 Phase 2 약효 확인** (C3): Phase 1 의 σ_normal_intra −45% 가 Phase 2 에서 +1% 로 효과 거의 사라짐. PSNR 40+ 의 강한 photometric supervision 이 normal 을 이미 정렬해 redundant 가설.

**다음 단계 (1-2 주 내)**:
1. Step 1 — Stage 2 group_id 를 Stage 3 입력으로 전달하는 인터페이스 정렬 (4-6 시간 작업)
2. 진짜 Stage 3 알고리즘 천장 재측정 (cos_thresh sweep 또는 GT direct 활용)
3. C3 진단 (L_normal_align gradient norm 분석)
4. 정정된 측정 위에서 Phase 2 결론 확정 → Phase 3 진입

**위험 요소**:
- 인터페이스 정렬 후에도 4 조건 차이가 미미할 경우 thesis 의 "메커니즘 2 → CityGML 개선" claim 약화 → "강한 supervision 환경에서는 효과 둔화" 로 thesis 재정의 검토 필요
- Phase 3 (real UAV) 의 시간 압박 — Phase 2 결론이 6 월 초까지 확정되어야 일정 여유

---

## 1. 연구 배경 및 동기

### 1.1 도시 규모 3D 건물 재구성의 의의

LOD2 CityGML (지붕 형태 포함 의미론적 3D 건물 모델) 은 디지털 트윈, 도시 시뮬레이션, 에너지 분석, BIM 등에 핵심 입력. 기존 데이터 구축은 *수동 모델링* 에 의존 — 도시 단위 자동화가 풀어야 할 과제.

이미지 기반 자동 재구성의 두 흐름:
- **순차 파이프라인**: SfM/MVS → RANSAC plane fitting → polygon assembly (e.g., City3D, PolyFit). 각 단계가 독립 — 상위 단계 오류가 하위로 전파, 의미론과 기하가 분리됨.
- **학습 기반 (미분 가능 렌더링)**: 3DGS / 2DGS 위에 평면화·구조 사전 (e.g., PlanarSplatting, CityGSV2, ULSR-GS, AGS). 의미론과 기하를 한 모델 안에서 다룰 수 있음.

### 1.2 기존 학습 기반 접근의 한계

| 접근 | 제한점 |
|---|---|
| PlanarSplatting | 의미론 부재 — wall/roof 구분 못 함 |
| CityGSV2 | depth/normal 감독, 의미론 미통합 |
| ULSR-GS | depth/normal + segmentation 통합되었으나 **각 모듈이 독립** — 면 단위 구조 정합 부재 |
| AlignGS | 면 정렬은 다루나 grouping 정의가 보조적 |

공통 한계: **의미론과 기하가 같은 변수에서 *동시에* 학습되지 않음**. 예: wall 임을 안다고 해서 그 wall 의 normal 이 자동으로 수직이 되는 메커니즘이 없음.

### 1.3 본 연구의 위치

> **미분 가능 렌더링 (gsplat + 2DGS) 위에 두 수준의 공동 최적화를 도입하여 의미론↔기하의 동시 교정을 구현하고, 이로부터 LOD2 CityGML 품질이 개선되는지를 검증한다.**

핵심 idea:
- Intra-primitive (메커니즘 1, *L_mutual*): "벽이면 수직, 지면이면 수평" 같은 **개별 프리미티브의 도메인 규칙**. p_c × 기하오차 의 곱 → 의미론(p_c)과 기하(n_i) 양방향 gradient.
- Inter-primitive (메커니즘 2, *L_structure*): 매 T iter 그룹핑 후 **그룹 내 법선/평면 정렬**. n_i, c_i 가 그룹 대표 평면으로 수렴.

두 메커니즘이 *같은 파라미터 (n_i)* 에 *동시에* gradient 를 더하는 구조. 이 동시 작용 + 주기적 재할당의 순환이 순차 파이프라인과의 근본적 차이.

---

## 2. 연구 질문 및 가설

### 2.1 핵심 가설

| 가설 | 내용 | 검증 단계 |
|---|---|---|
| **H1** | 도메인 규칙 (intra-primitive) 이 primitive 수준 quality 를 개선한다 (wall 법선 수직성, terrain 수평성, semantic 정합) | Phase 1 (MatrixCity), 검증 완료 |
| **H2** | 구조 정합성 (inter-primitive) 이 primitive 수준 quality 를 개선한다 (그룹 내 법선/평면 분산 감소) | Phase 1 검증 완료 (단, Phase 2 에선 약함 — §5.5 참조) |
| **H3** | H1 + H2 가 LOD2 CityGML 품질 (val3dity, 면 정합도, semantic 정확도) 개선으로 이어진다 | Phase 2 (3D BAG), **진행 중** |
| **H4** | 위 효과가 real UAV 데이터에서도 재현되며, 순차 파이프라인 (City3D 등) 보다 우월하다 | Phase 3 (GauU-Scene + 성수동), 미착수 |

### 2.2 검증 단계 설계 (Phase 1/2/3)

| Phase | 데이터 | GT 강도 | 측정 가능 | 입증 대상 |
|---|---|---|---|---|
| **1** | MatrixCity (도시 합성) | depth/normal 규칙 pseudo-label (약) | 렌더 parity, Wall-vert%, σ_normal, mIoU | H1, H2 |
| **2** | 3D BAG (건물 합성) | CityGML 자체 (강) | val3dity, 면 IoU, Hausdorff, semantic acc | H3 |
| **3** | GauU-Scene + 성수동 (real UAV) | 없음 | 순차(City3D) 대비 시각·정량 비교 | H4 |

각 Phase 는 직전 결과 위에서만 의미 있음 → 순차 진행. Phase 1 통과 없이 Phase 2 의미 없고, Phase 2 결론 없이 Phase 3 의미 없음.

---

## 3. 방법론

### 3.1 파이프라인 개요

| Stage | 역할 | 입력 | 핵심 처리 | 출력 |
|---|---|---|---|---|
| **Stage 1** | 사전 추정 | 멀티뷰 이미지 | SfM/MVS, semantic segmentation, gravity 추정 | depth, mask, gravity 벡터 |
| **Stage 2** | **공동 최적화 (본 연구의 핵심)** | Stage 1 출력 + 이미지 | gsplat + 2DGS + L_mutual (메커니즘 1) + L_structure (메커니즘 2) | 평면 프리미티브 $\{c_i, n_i, s_i, f_i, sh_i\}$ |
| **Stage 3** | CityGML 변환 | Stage 2 프리미티브 | 그룹핑 → 대표평면 → 평면 교차 → ConvexHull | LOD2 CityGML + val3dity 검증 |

본 연구의 **새로운 기여는 Stage 2** 이며, Stage 1, 3 은 표준 + 약간 변형. 실험에서는 4 조건 ablation 으로 Stage 2 의 메커니즘 효과만 변화시키고 나머지 stage 는 동일.

### 3.2 Stage 2 — 공동 최적화

#### 평면 프리미티브 (Gaussian splat 변형)

| 변수 | 차원 | 의미 |
|---|---|---|
| c_i | (N, 3) | 중심 |
| n_i | (N, 3) | 법선 = normalize(t_u × t_v) |
| s_i | (N, 2) | in-plane scale |
| f_i | (N, 4) | semantic logits (BG/Roof/Wall/Terrain) |
| sh_i | (N, C) | SH 색상 계수 |
| opacity_i | (N, 1) | 불투명도 |

#### 전체 손실 함수

$$L = L_{photo} + L_{depth} + L_{normal} + \lambda_{nc} L_{nc} + \lambda_{s} L_{sem} + \lambda_{m} L_{mutual} + \lambda_{str} L_{structure}$$

| 손실 | 작용 변수 | 역할 |
|---|---|---|
| L_photo | 모든 변수 | L1 + SSIM (rendering) |
| L_depth | c_i | MVS depth L1 |
| L_normal | n_i | MVS normal cosine |
| L_nc | n_i, c_i | rendering normal ≈ depth-derived normal |
| L_sem | f_i | CrossEntropy (ignore_index=BG) |
| **L_mutual** | n_i, f_i, c_i (높이만) | **메커니즘 1, intra-primitive** |
| **L_structure** | n_i, c_i | **메커니즘 2, inter-primitive** |

#### 메커니즘 1: L_mutual (intra-primitive 도메인 규칙)

$$L_{mutual} = \sum_i \left[ p_{wall} \cdot (n_i \cdot e_g)^2 + p_{roof} \cdot \mathrm{ReLU}(\tau - (n_i \cdot e_g)^2)^2 + p_{terrain} \cdot (1 - |n_i \cdot e_g|)^2 + L_{height} \right]$$

여기서 $p_c = \mathrm{softmax}(f_i)$, $e_g$ = gravity 벡터 (Stage 1 에서 사전 추정).

| Component | 의미 | 수렴 방향 |
|---|---|---|
| 1st | wall 의 법선이 gravity 와 수직 | $n_i \perp e_g$ |
| 2nd | roof 의 법선은 수평 (slope 작음) | $|n_i \cdot e_g| > \sqrt{\tau}$ |
| 3rd | terrain 의 법선은 수직 (gravity 와 평행) | $|n_i \cdot e_g| \to 1$ |
| L_height | roof 의 평균 높이 > terrain 의 평균 높이 | c_i 의 z 성분에만 작용 |

**핵심 양방향성**: $p_c \times$ 기하오차 의 곱 형태 → $\partial L_{mutual} / \partial f_i \neq 0$ 와 $\partial L_{mutual} / \partial n_i \neq 0$ 동시 성립. 즉 *의미론을 알면 기하가 교정*되고, *기하가 정확하면 의미론이 강화*됨.

#### 메커니즘 2: L_structure (inter-primitive 구조 정합)

매 $T$ iteration 마다 그룹핑 수행:
- 그룹 키: (semantic class, voxel_3d, normal direction quantized)
- 그룹 별 대표 평면 $\Pi_k = (n_k, d_k)$, 가중 평균 (weight = max in-plane scale)

$$L_{normal\_align} = \sum_k \sum_{i \in G_k} (1 - n_i \cdot n_k)^2 \quad (n_k \text{ detach})$$

$$L_{coplanar} = \sum_k \sum_{i \in G_k} (n_k \cdot c_i + d_k)^2 \quad (n_k, d_k \text{ detach})$$

$$L_{structure} = \lambda_{na} L_{normal\_align} + \lambda_{cp} L_{coplanar}$$

**$f_i$ 에 직접 gradient 없음**. 그룹 할당이 $\mathrm{argmax}(f_i)$ 의 이산 연산이라 $\partial L_{structure} / \partial f_i = 0$. $f_i$ 교정은 메커니즘 1 이 담당, 그룹 재할당이 간접 피드백.

#### 두 메커니즘의 동시 작용 (순차 파이프라인과의 차이)

매 iteration 에서 $n_i$ 에 대한 gradient:

$$\frac{\partial L}{\partial n_i} = \frac{\partial L_{photo}}{\partial n_i} + \frac{\partial L_{normal}}{\partial n_i} + \cdots + \frac{\partial L_{mutual}}{\partial n_i} + \frac{\partial L_{normal\_align}}{\partial n_i}$$

하나의 파라미터에 *도메인 규칙* ("벽이니까 수평") 과 *면 단위 정렬* ("같은 면이니까 같은 방향") 이 동시에 합산됨. 메커니즘 2 의 정렬 → 메커니즘 1 의 정렬된 normal 로 의미론 교정 → 교정된 의미론이 다음 그룹 재할당에 반영. **이 순환이 순차 파이프라인과의 근본 차이.**

#### 학습 전략 (warmup)

| 구간 | iteration | 활성 손실 |
|---|---|---|
| 초기 | $0 \sim N/3$ | $L_{photo} + L_{depth} + L_{normal} + L_{nc} + L_{sem}$ |
| 중기 | $N/3 \sim 2N/3$ | $+ L_{mutual}$ |
| 후기 | $2N/3 \sim N$ | $+ L_{structure}$ |

L_structure 가 늦게 활성화되는 이유: 안정된 $n_i, f_i$ 위에서 그룹핑이 의미 있어짐.

### 3.3 Stage 3 — CityGML LOD2 변환

평면 프리미티브 → LOD2 polytope:

```
1. 분류 + 필터        : opacity threshold, semantic class 별 분리
2. Multi-primitive 클러스터링 : cos > 0.85 + 공간 근접 (현재 hierarchical)
3. 클러스터 → 대표 평면      : 가중 평균 + ground/bbox 보강
4. 평면 교차 → convex polytope : half-space intersection + ConvexHull
5. Ground surface 부착
6. CityJSON export + val3dity 검증
```

핵심 평가 지표 (Stage 3 출력 단위):
- **val3dity**: ISO 19107 위상 valid 여부 (binary). ledoux et al. 2018 도구 표준.
- **면 IoU**: 매칭된 pred face vs GT face 의 2D polygon overlap.
- **Hausdorff distance**: pred mesh vs GT mesh 양방향 표면 거리.
- **Semantic accuracy**: 매칭 pair 의 class label 일치율.

---

## 4. Phase 1 결과 — 메커니즘 단위 검증 (MatrixCity)

### 4.1 목적과 scope

Phase 1 의 역할은 **메커니즘 단위 검증**:
1. 2DGS 기반 재구성이 외부 레퍼런스 (CityGSV2 PSNR 21.12) 수준인지
2. L_mutual, L_structure 가 *설계대로* 작동하는지
3. Both 구성이 *학습 가능* 하고 두 효과를 *동시 보존* 하는지

**Phase 1 scope 가 *아닌 것*** : 시너지 / 간섭 / CityGML 품질 / 순차 대비 우위 (모두 Phase 2/3).

### 4.2 6 단계 점진 검증 (체크리스트)

데이터: MatrixCity Small City Aerial, 5,621 장 + COLMAP sparse, 30k iter.

| Step | 검증 목표 | 레퍼런스 / 설계 | 결과 | 통과 |
|---|---|---|---|---|
| 1-1 | Vanilla 2DGS parity | CityGSV2 baseline PSNR 21.12 | 21.31 | ✓ |
| 1-2 | + Depth/Normal 감독 parity | CityGSV2 w/depth 22.22 | 22.06 (peak 22.39) | ✓ |
| 1-3 | + Semantic head 비파괴 | Step 1-2 PSNR 유지 | 22.07, mIoU 0.635 | ✓ |
| 1-4 | L_mutual 작동 | Wall-vert% 상승 | **16.9% → 88.2%** | ✓ |
| 1-5 | L_structure 작동 | σ_normal 감소 | **−45%** | ✓ |
| 1-6 | Both 공존 | 렌더/기하 + WV + σ | PSNR 20.63, F1 0.999, WV 88.3%, σ_n −36% | ✓ |

**6/6 통과** — Phase 1 의 모든 검증 기준 충족.

### 4.3 메커니즘 1 (L_mutual) 의 효과 — 도메인 규칙

**왜 이 지표를 보는가**: L_mutual 의 설계 목표가 "wall = 수직, terrain = 수평, roof = 수평" 의 도메인 규칙 강제. 따라서 wall-class primitive 중 *실제로 수직인* 비율이 메커니즘 작동의 직접 증거.

| 지표 | 정의 | 방향 | Baseline | Mutual | Structure | Both |
|---|---|---|---|---|---|---|
| **Wall-vert %** | wall-class 중 \|n·g\|<0.15 (g=gravity) 비율 | ↑ | 16.9% | **88.2%** | 17.0% | **88.3%** |
| Terrain-horiz % | terrain-class 중 \|n·g\|>0.85 비율 | ↑ | 93.4% | **99.0%** | 95.3% | **99.1%** |
| Roof-horiz % | roof-class 중 \|n·g\|>0.85 비율 | ↑ | 88.9% | 49.0%* | 91.8% | 54.3%* |

**어디를 보라**: Wall-vert % 가 Baseline 17% → Mutual/Both 88% 로 약 5 배 점프. Structure 단독 (17%) 은 무영향 — 메커니즘 정의대로 메커니즘 1 만의 효과.

*Roof-horiz 감소 caveat: L_mutual 이 ambiguous primitive 를 BG (ignore) 로 재할당하여 Wall-class 가 31.4% → 12.5% 로 줄어듦. 이 과정에서 일부 경사면이 Roof 로 재분류되어 분모 (Roof-class) 에 비수평 요소 혼입. **artifact 가 아닌 설계대로의 동작** (Phase 1 REPORT §6.5 상세).

**시각 증거** (4 view × 6 column 비교):

![phase1_semantic_4way](../results/phase1_ablation/figures/semantic_compare_4way/semantic_compare_4way.png)

**위 그림 읽는 법**:
- **6 columns (좌→우)**: RGB_GT | GT_sem | Baseline | Mutual | Structure | Both
- **4 rows (위→아래)**: 4 개의 다른 view (5083, 5368, 5328, 5528)
- **색상 의미**: 검정=BG (ignore), 빨강=Roof, **파랑=Wall**, 초록=Terrain
- **어디를 보라**: 각 row 에서 *2열 (GT_sem)* 와 *3열 (Baseline)* 비교 → Baseline 이 잘못 분류한 영역 확인. 그 다음 *5열 (Structure)* 보면 Baseline 과 거의 동일 (메커니즘 2 는 의미론 미관여), *4열 (Mutual)* 과 *6열 (Both)* 에서 GT 와 가까워짐
- **왜 이 그림을 보는가**: Wall-vert 16.9% → 88.3% 의 *수치적* 점프가 *공간적으로* 어떻게 나타나는지 — Baseline 이 Wall 로 잘못 부르던 영역이 Mutual/Both 에서 정확한 class 로 재분류되는 패턴을 4 view 에 걸쳐 확인 가능
- **Phase 2 함의**: Baseline 은 지붕/지면 등에 WallSurface 폴리곤 생성, Mutual/Both 는 정확한 RoofSurface/GroundSurface 생성 → CityGML 의미론 정합도 차이로 직결

### 4.4 메커니즘 2 (L_structure) 의 효과 — 그룹 정합

**왜 이 지표를 보는가**: L_structure 의 설계 목표가 "같은 그룹 내 법선/평면 정렬". 따라서 그룹 내 분산 (σ) 감소가 메커니즘 작동의 직접 증거.

| 지표 | 정의 | 방향 | Baseline | Mutual | Structure | Both |
|---|---|---|---|---|---|---|
| **σ_normal_intra** (deg) | 그룹 내 법선의 평균 mean 으로부터의 각도 분산 | ↓ | (base) | -2% | **−45%** | **−36%** |
| σ_coplanar (m) | 그룹 내 center 의 대표 평면까지 거리 분산 | ↓ | (base) | -3% | **−16%** | -12% |

**어디를 보라**: σ_normal_intra 가 Structure/Both 에서 −36~−45% 로 *대폭 감소*. Mutual 단독은 무영향 — 메커니즘 2 의 정의대로.

![phase1_structure](../results/phase1_ablation/figures/structure_4way_bars.png)

**위 그림 읽는 법**:
- 4 조건 × 2 지표 (σ_normal_intra, σ_coplanar) bar chart
- **어디를 보라**: 좌측 σ_normal_intra 막대 — Structure/Both 가 Baseline/Mutual 대비 절반 이하 (정합 강화). 우측 σ_coplanar 도 동일 패턴이나 magnitude 작음
- **왜 이 그림을 보는가**: 메커니즘 2 의 *그룹 정합 효과* 가 시각적으로 명료함. 단독 (Structure) 에서 효과가 더 큼 — Both 에서는 L_mutual 의 BG 재할당이 그룹 구성을 약간 흩어 magnitude 약간 감소

### 4.5 Both 조건 — 두 메커니즘 공존 검증

**왜 이 표를 보는가**: 메커니즘 1, 2 가 *같은 변수 (n_i)* 에 동시에 gradient 를 더하는 구조라 서로 *간섭* 할 위험 (한 메커니즘이 다른 메커니즘을 무력화) 이 있음. 따라서 Both 에서 두 효과가 *동시 보존* 되는지 확인이 필수.

| Metric | 정의 / 방향 | Baseline | Mutual | Structure | Both | 판정 |
|---|---|---|---|---|---|---|
| PSNR [dB] | rendering 품질, ↑ | 20.51 | 20.63 | 20.62 | **20.63** | 추가 손실이 기본 복원 안 해침 |
| F1 @ 0.5m | 점밀도 정합도, ↑ | 0.998 | 0.998 | 0.999 | **0.999** | near-perfect 동등 |
| Chamfer [m] | mesh 거리, ↓ | 0.021 | 0.023 | 0.020 | 0.022 | ±10% 동등 |
| Wall-vert % | 메커니즘 1 효과, ↑ | 16.9 | 88.2 | 17.0 | **88.3** | **Mutual 효과 Both 에 보존** |
| σ_normal | 메커니즘 2 효과, ↓ | (base) | — | −45% | **−36%** | **Structure 효과 Both 에 보존** |

**어디를 보라**: 마지막 두 행 (Wall-vert, σ_normal) 의 Both 칸. Both 가 단독 조건과 비슷한 magnitude 를 유지 → 두 효과 공존 입증.

**Photometric parity 시각 증거**:

![phase1_render_4way](../results/phase1_ablation/figures/render_compare_4way/render_compare_4way.png)

**위 그림 읽는 법 + 왜 보여주는가**:
- 4 조건 (Baseline / Mutual / Structure / Both) 의 같은 view RGB rendering 을 좌→우로 나열
- **시각적으로 거의 구분 불가능한 것이 *증거*** — 추가 손실 (L_mutual, L_structure) 을 도입했음에도 photometric quality 가 baseline 대비 손상되지 않았음을 보여줌
- 즉 "Both 가 Baseline 과 시각적으로 같다 = 추가 손실이 rendering 을 안 해친다"
- 이게 없으면 "L_mutual 이 wall 을 수직화하는 대가로 RGB 가 흐려졌을 가능성" 을 배제 못함 → falsifiability 차원의 증거

### 4.6 Phase 1 종합 — Contribution Decomposition

**왜 이 그림을 보는가**: 6 단계 (1-1 부터 1-6) 의 점진 추가가 *각각* 어떤 metric 에 기여했는지 한눈에 보여줌.

![phase1_contribution](../results/phase1_ablation/figures/contribution_decomposition.png)

**위 그림 읽는 법**:
- x 축: Step 1-1 (vanilla 2DGS) → 1-2 (+depth/normal) → 1-3 (+sem) → 1-4 (+L_mutual) → 1-5 (+L_structure) → 1-6 (Both)
- y 축: 각 metric (PSNR, Wall-vert%, σ_normal 등) 의 변화
- **어디를 보라**: 
  - PSNR 은 1-1~1-3 까지 증가 (depth/normal 감독 효과), 이후 안정 (메커니즘 추가가 안 해침)
  - Wall-vert% 는 1-4 (+L_mutual) 에서 jump
  - σ_normal 은 1-5 (+L_structure) 에서 drop
- **결론**: 각 메커니즘이 *자기 metric* 에 영향, *다른 metric* 보존 → 모듈 별 contribution 명확

### 4.7 Phase 1 결론

- 두 메커니즘이 **각각 의도대로** 작동 (Wall verticalization, group alignment).
- Both 에서 **두 효과 동시 보존**, 학습 안정.
- **렌더링/기하 parity 유지** — 추가 손실이 기본 reconstruction quality 안 해침.
- → Phase 2 입력 (4 조건 ckpt) 적합성 확인.

**판정 보류**: 시너지·간섭 여부, CityGML 품질 영향 — Phase 2 측정으로 이관.

---

## 5. Phase 2 결과 — CityGML 품질 평가 (3D BAG)

### 5.1 데이터 및 실험 설계

| 항목 | 값 |
|---|---|
| 데이터 | 3D BAG Amsterdam Jordaan, 131 건물 합성 렌더링 |
| GT | CityGML 자체 (RoofSurface/WallSurface/GroundSurface) |
| Roof type 분포 | flat 25, gable 28, hip 23, complex 29, tri-slope 26 |
| Stage 2 | 4 조건 × 30k iter, ~988K primitives/condition |
| Stage 3 | Convex polytope (모든 조건 동일) |
| 평가 | val3dity, 면 IoU, Hausdorff, Semantic accuracy |

### 5.2 Stage 2 결과 — Primitive 수준 (Phase 1 효과 전이 확인)

#### Rendering quality (4 조건 parity)

**왜 이 표를 보는가**: Phase 1 과 동일하게, 추가 손실이 photometric 을 안 해치는지 sanity check. 4 조건이 비슷해야 통과.

| Condition | eval PSNR | 판정 |
|---|---|---|
| Baseline | 40.35 | 4 조건 모두 PSNR 40 saturation — 합성 데이터의 강한 supervision |
| Mutual | 40.93 | 추가 손실이 photo 안 해침 ✓ |
| Structure | 40.96 | 동등 ✓ |
| Both | 39.81 | 약간 낮으나 ±0.5 dB 이내 ✓ |

**Phase 1 (PSNR 22) vs Phase 2 (PSNR 40+) 의 차이**: 3D BAG 합성 데이터는 노이즈 거의 없는 ideal renderer 출력 → photometric 만으로 normal 까지 거의 정확하게 정렬됨. **이 차이가 §6.3 의 L_normal_align 약효 가설의 핵심 배경.**

(SSIM/LPIPS/F1/Chamfer 등 추가 지표는 미측정 — Phase 2 에선 val3dity 가 main metric 이라 Phase 1 만큼 상세히 안 잡았음. 필요 시 추가 측정 가능 — 1 시간.)

#### Primitive 구조 지표 (Stage 3 의 *입력* 직접 측정)

**왜 이 표를 보는가**: Phase 1 의 메커니즘 효과 (Wall vert ↑, σ_normal ↓) 가 Phase 2 데이터에서도 재현되는지가 H1, H2 의 Phase 2 검증.

| 지표 | 정의 | 방향 | Baseline | Mutual | Structure | Both | Phase 1 비교 |
|---|---|---|---|---|---|---|---|
| **Wall vertical-frac** | wall-class 중 \|n·g\|<0.15 | ↑ | 28.0% | **79.3%** | 28.4% | **79.4%** | Phase 1 17→88% 와 같은 방향, magnitude 약간 작음 |
| Roof horizontal-frac | roof-class 중 \|n·g\|>0.85 | ↑ | 56.3% | 54.1% | 56.5% | 54.3% | 변화 없음 (Phase 1 과 유사) |
| σ_normal_intra (deg) | 그룹 내 법선 분산 | ↓ | 14.74 | 12.63 | **14.88** | 12.99 | **Phase 1 Structure −45%, Phase 2 +1%** ← 약효 발견 |
| σ_coplanar (m) | 그룹 내 평면 정합 | ↓ | 1.91 | 1.84 | **1.86** | 2.01 | Phase 1 −16%, Phase 2 −2~−9% (Coplanar 는 약하게 작동) |

**어디를 보라**:
- 1행 (Wall vertical-frac): Mutual/Both 에서 28% → 79% — **메커니즘 1 의 Phase 2 작동 확인 ✓**
- 3행 (σ_normal_intra): Structure 가 Baseline 보다 *오히려 약간 ↑* (+1%) — **메커니즘 2 의 L_normal_align component 가 Phase 2 에서 거의 작동 안함** (Phase 1 의 −45% 와 극명한 대조)
- 4행 (σ_coplanar): Structure −2~−9% — **L_coplanar component 는 약하게나마 작동**

**핵심 해석**:
- L_mutual: Phase 1 → Phase 2 **부분 전이** (27→79%, OK)
- L_normal_align: Phase 1 → Phase 2 **거의 사라짐** (-45% → +1%) ← **C3 모순, §5.5 에서 분석**
- L_coplanar: Phase 1 → Phase 2 **약화이나 작동** (-16% → -5%)

### 5.3 Stage 3 결과 — CityGML 출력 (4 조건 ablation, post-fix)

**왜 이 표를 보는가**: H3 ("메커니즘 1+2 가 CityGML 품질 개선") 의 직접 측정. val3dity 가 binary 합격 여부 (가장 엄격), 면 IoU 와 sem acc 는 매칭 기반 정합도, Hausdorff 는 mesh 거리, σ_normal 은 그룹 정합도.

| Condition | val3dity pass ↑ | face IoU ↑ | Hausdorff (m) ↓ | Sem acc ↑ | σ_normal (deg) ↓ |
|---|---|---|---|---|---|
| **Baseline** | 52.7% (69/131) | 0.214 | 11.37 | 21.6% | 9.09 |
| **Mutual** | 48.9% (64/131) ↓ | **0.240** ↑ | 11.54 | 20.6% | **8.73** ↑ |
| **Structure** | **55.0%** (72/131) ↑ | 0.221 | 11.45 | **22.0%** ↑ | 9.18 |
| **Both** | 54.2% (71/131) ↑ | 0.227 | 11.56 | 20.4% | 9.00 |

**어디를 보라**:
- val3dity (1열): **Structure > Both > Baseline > Mutual** — 메커니즘 2 우세, Mutual 이 단독으론 회귀
- face IoU (2열): Mutual 최고이나 §5.4 caveat 적용 — 신뢰도 낮음
- σ_normal 3D (5열): Mutual 이 가장 낮음 — wall 수직화의 *Stage 3 출력에서의 기하 효과* 직접 확인
- Sem accuracy (4열): 모든 조건 21% 수준 — *낮아 보이나 metric 가혹성 때문* (§5.4 의 GT_convex 비교에선 46% 수준), **상대 비교만 의미**

**조건별 ranking 종합 (val3dity 기준)**: Structure > Both > Baseline > Mutual
- 메커니즘 2 (Structure) 가 일관 최상위
- 메커니즘 1 단독 (Mutual) 은 회귀 — §5.4-5.5 의 인프라 + 인터페이스 문제와 관련

#### Type 별 패턴

| Type | Baseline | Mutual | Structure | Both | 패턴 |
|---|---|---|---|---|---|
| complex (29) | 58.6% | 51.7% | **69.0%** | 65.5% | Structure/Both ↑ |
| hip (23) | 43.5% | 52.2% | **56.5%** | 52.2% | Mech 모두 ↑ |
| tri-slope (26) | 38.5% | 42.3% | 50.0% | **53.8%** | Mech 모두 ↑ |
| gable (28) | **64.3%** | 53.6% | 57.1% | 53.6% | Baseline 최고, 모든 Mech ↓ |
| flat (25) | **56.0%** | 44.0% | 40.0% | 44.0% | Baseline 최고, 모든 Mech ↓ |

- 복잡 건물 (complex/hip/tri-slope): Structure/Both 가 +10~17%p
- 단순 건물 (flat/gable): 모든 메커니즘이 Baseline 보다 낮음

![phase2_type](../results/phase2_ablation_citygml/figures/fig7_type_vs_condition.png)

**위 그림 읽는 법**:
- x 축: roof type (complex, gable, hip, tri-slope, flat). y 축: val3dity 통과율 (%)
- 4 조건이 각각 다른 색 막대 (Baseline/Mutual/Structure/Both)
- 점선 = GT direct 천장 (93.9%), 파선 = GT convex 천장
- **어디를 보라**:
  1. **complex/hip/tri-slope (좌측 3 그룹)**: Structure/Both 막대가 Baseline 보다 높음 → 메커니즘 2 효과
  2. **flat/gable (우측 2 그룹)**: Baseline 막대가 가장 높음, 모든 메커니즘이 회귀 → 단순 건물 과조정 (D' 가설)
- **caveat 1**: 막대 magnitude 는 v3 (pre-fix) 기반 — v4 에선 모든 조건 +10~17%p. **상대 패턴은 동일**
- **caveat 2**: 파선 (GT convex 천장) 자체에 §5.4 의 측정 오류 — *진짜 천장 위치는 미정*

### 5.4 결과 신뢰도 — 발견된 두 가지 측정 인프라 오류

§5.3 결과를 어떻게 읽어야 하는지 정직하게 짚어둘 점. 작업 중 두 건의 측정 인프라 오류가 발견됨:

| # | 오류 | 영향 | 상태 |
|---|---|---|---|
| **(1)** | `bbox_margin` 1 줄 버그 (Stage 3 polytope 구성) | v3 측정값이 +10~17%p 왜곡, 정정 후 v4 가 §5.3 표 | **수정 완료** (2026-04-25) |
| **(2)** | GT_convex 가 GT 의 약 절반 높이로 축소 (88% 건물) | v4 의 "Stage 3 천장 96.2%" 가 잘못된 reference | **수정 미완**, 천장 재측정 필요 (§7.2) |

**오류 (2) 의 직접 검증 (building 1)**:

| | 높이 |
|---|---|
| GT mesh 원본 | 16.61m |
| **우리 Stage 3 출력** | 16.41m ← GT 와 거의 일치 |
| GT_convex (잘못된 reference) | 8.56m (절반) |

→ 우리 Stage 3 출력 자체는 *GT 와 비슷한 크기* 를 만들어내고 있고 시각적 인상과 부합. 단지 비교 대상 (GT_convex) 이 GT 를 절반으로 축소시켜놓아 metric 해석이 흐려진 상태.

**시사점**:
- §5.3 의 4 조건 *상대 ranking* (Structure ≥ Both > Baseline > Mutual) 은 valid — 모두 같은 알고리즘 거침
- *천장 대비 절대 격차* 는 미정 → §7.2 에서 재측정 후 결정
- 1 줄 수정으로 conclusion 이 흔들리는 fragility 자체가 시사점 — 학위 논문의 *reproducibility* contribution 후보

상세 진단 데이터는 `results/phase2_ablation_citygml/REPORT.md` (v4) §2, §5.5 참조.

### 5.5 발견된 모순 — 코드 구조 (C2, C3)

#### C2: Stage 2 ↔ Stage 3 인터페이스 단절

| | 알고리즘 | grouping 키 |
|---|---|---|
| Stage 2 (`src/stage2/grouping.py`) | voxel hash, 매 T iter | (class, voxel_3d, normal_dir_quantized) |
| Stage 3 (`src/stage3/clustering.py`) | hierarchical (cos > 0.92) + spatial split | normal-only, 학습 시 group 정보 무시 |

**즉 L_structure 가 학습 내내 만든 group 정보 (group_id, rep_n, rep_d) 가 Stage 3 에 전달되지 않고 통째로 버려지고 재계산됨.** 메커니즘 2 의 효과가 Stage 3 측정에서 부분적으로만 드러나는 구조적 원인.

#### C3: L_normal_align 의 Phase 2 약효

**관찰**: Phase 1 σ_normal_intra −45% → Phase 2 +1%. L_coplanar 는 약하나마 작동 (-2~-9%) 하지만 *L_normal_align component 만* 효과 거의 사라짐.

**가설 (미검증)**: PSNR 40+ 의 강한 photometric supervision 이 normal 을 이미 정렬해 L_normal_align 이 redundant. 학습 trajectory 상 normal 이 일찍 수렴 → L_normal_align 이 추가 이동시킬 여지 없음.

**현재 상태**: **본 가설은 미검증**. 검증 방법:
- Structure ckpt 의 학습 마지막 50 iter σ_normal_intra trajectory dump
- 빠르게 saturate → photo loss 가설 지지
- 끝까지 진행 안 함 → 다른 원인 (예: gradient 희석, grouping 부정확)
- 작업량: 1 시간

**§7.3 (다음 단계) 에서 진행 예정.** 결과에 따라 thesis 의 *supervision-strength conditional* claim 로 정직 보고할지 결정.

### 5.6 Phase 2 잠정 결론

**확정된 진행 (긍정)**:
1. Stage 2 메커니즘 1 의 wall 수직화 효과가 Phase 2 에 부분 전이 (28→79%)
2. 4 조건 ablation 의 *상대 비교* 는 valid: Structure ≥ Both > Baseline > Mutual (val3dity 기준)
3. 복잡 건물에서 메커니즘 2 의 +10~17%p 개선 일관 관찰

**미확정 (보류)**:
1. Stage 3 algorithm 의 진짜 천장 (GT_convex 측정 오류로 미정)
2. 우리 best 55.0% 의 천장 대비 절대 위치
3. C1 잔존 회귀 (-3.8%p) 의 진짜 원인 (D' 가설: 단순 건물 과조정)
4. 시너지 / 간섭 — Both ≤ Structure 인 이유

**메타 발견**:
- Stage 3 측정 인프라의 fragility — 두 차례의 1-줄 단위 측정 오류 (bbox, GT_convex) 가 conclusion 을 뒤집음
- 인프라 안정화가 Phase 2 결론 확정의 전제

---

## 6. 핵심 발견 및 함의

### 6.1 메커니즘은 *primitive 수준* 에서 의도대로 작동

Phase 1, 2 모두에서 일관 검증:

| 메커니즘 | Phase 1 (MatrixCity, PSNR 22) | Phase 2 (3D BAG, PSNR 40+) |
|---|---|---|
| L_mutual: Wall verticalization | 17% → 88% | 28% → 79% |
| L_mutual: Terrain 수평화 | 93% → 99% | (측정 시 효과 유사) |
| L_structure: σ_normal 감소 | **−45%** | +1% (약효 — C3) |
| L_structure: σ_coplanar 감소 | −16% | −2~−9% |

H1 (메커니즘 1) 은 **양 phase 에서 강하게 입증**. H2 (메커니즘 2) 는 Phase 1 에서 입증, Phase 2 에서 **약화** (PSNR 40+ supervision 이 normal 을 이미 정렬한 가설).

### 6.2 Stage 3 알고리즘 자체는 *충분히 강함* (잠정)

GT direct (topology 보존) val3dity 통과율 = **93.9%**. 즉 GT mesh 의 topology 만 보존하면 거의 모든 건물이 valid CityGML 가능. 알고리즘 능력의 잠재 천장이 매우 높음.

**단**: convex polytope 의 구체적 천장은 GT_convex 측정 오류로 미정. 정확한 알고리즘 천장 재측정 필요 (§7).

### 6.3 진짜 병목 = Stage 2→3 인터페이스 + 단순 건물 과조정

#### Bottleneck 1: 인터페이스 단절 (C2)

L_structure 가 학습 내내 만든 group 정보를 Stage 3 가 통째로 버리고 자기 알고리즘으로 재계산. 메커니즘 2 의 "inter-primitive 정합성" 정의가 Stage 3 동작과 *불일치*.

연구 의도 측면: thesis 의 핵심 claim ("inter-primitive 정합성이 CityGML 품질 개선") 이 Stage 3 출력에서 부분적으로만 측정 가능한 구조적 한계.

#### Bottleneck 2: 단순 건물에서의 과조정

flat/gable (단순 박스 건물) 에서 모든 메커니즘이 Baseline 보다 낮음 (Mutual −12%p, Structure −16%p).

가설: baseline primitive 도 단순 건물엔 충분히 수직, 추가 정렬이 polytope 안정성 손상 (D' 가설). 즉 메커니즘이 *일관 ↑* 가 아니라 *복잡 건물에서만 ↑, 단순 건물에서는 ↓* 라는 building complexity-dependent 효과.

### 6.4 Measurement 인프라의 fragility

두 차례의 1-줄 단위 측정 오류 (bbox_margin 자동화, GT_convex grouping cos_thresh) 가 다음을 일으킴:
- v3 conclusion ("Mutual 회귀 −8.4%p") 의 절반이 인프라 artifact
- v4 conclusion ("Stage 3 천장 96.2%") 자체가 잘못된 reference

**시사점**: Stage 3 알고리즘 교체나 새 메커니즘 도입 같은 큰 변경의 결과를 신뢰하기 전에 *측정 인프라 stress test* 가 필요. 특히 polytope 알고리즘 같은 numerical-edge-case 에 민감한 모듈.

### 6.5 박사 thesis 의 contribution claim 위치

현재 시점 (2026-04-26) 에서 입증된 것:
1. 미분 가능 렌더링 + 의미론 + 도메인 규칙 + 구조 정합 의 통합 학습 framework (코드 + 검증)
2. L_mutual, L_structure 가 primitive 수준에서 작동 (Phase 1+2 양쪽)
3. Phase 2 에서 *복잡 건물* 의 CityGML 품질 개선 (Structure +10~17%p)

미입증 (Phase 2 마무리 + Phase 3 필요):
4. 위 효과가 단순 건물 포함 *전반적* CityGML 품질 개선으로 이어지는가
5. real UAV 데이터에서 재현되는가
6. 순차 파이프라인 (City3D 등) 대비 우월한가

---

## 7. 다음 단계 (1-2 주)

### 7.1 Step 1 — Stage 2→3 인터페이스 정렬 (메인, 4-6 시간)

**목표**: C2 해소. 메커니즘 2 의 출력 (group_id, rep_n, rep_d) 을 Stage 3 가 직접 사용.

**작업**:
1. `src/stage2/train.py` 마지막에 `group_primitives()` 호출, ckpt 에 group 정보 export
2. `src/stage3/clustering.py` 의 자체 grouping 제거 또는 wrapper 화
3. Stage 3 4 단계로 단순화: group → 대표평면 → 평면교차 → polygon
4. 4 조건 ckpt 모두에 적용 → CityGML 재생성 → val3dity 측정

**기대**: 
- C2 의 "정의-동작 불일치" 해소 → 메커니즘 2 효과의 정직한 측정
- Mutual 의 잔존 회귀 (−3.8%p) 가 추가 해소될 가능성 (Stage 3 자체 grouping 의 over-merge 도 함께 사라짐)

**검증**: Step 1 (1 시간) — 1 조건 ckpt 에 post-hoc grouping 적용, 학습 시 grouping snapshot 과 IoU 비교.

### 7.2 진짜 Stage 3 알고리즘 천장 재측정 (1-2 시간)

GT_convex 의 systematic 축소 원인 디버그 + 정정:
- `process_building(cos_thresh=1.0)` 으로 GT 다시 polytope 화 (face 합치기 비활성화) — 비교 측정
- 또는 GT direct 93.9% 를 알고리즘 천장의 lower bound 로 채택

진짜 천장이 정해지면 v5 REPORT 갱신 + 우리 best 의 천장 대비 위치 확정.

### 7.3 C3 진단 — L_normal_align Phase 2 약효 원인 (1 시간)

Photo loss redundancy 가설 검증:
- Structure ckpt 의 학습 마지막 50 iter σ_normal_intra trajectory dump
- 빠르게 saturate → photo loss 가설 지지 (thesis 부정 X)
- 끝까지 진행 안 함 → 다른 원인 (gradient 희석, grouping 부정확)

### 7.4 Phase 3 진입 (Step 1 완료 + Phase 2 결론 확정 후)

- **GauU-Scene** (real UAV, GT mesh 있음): Phase 2 와 동일 메커니즘으로 학습 + 평가
- **순차 파이프라인 비교** (City3D, PolyFit): joint > sequential 정량 입증
- **성수동 시연** (GT 없음): 질적 시각화 + 도시 단위 시연

---

## 8. 학위논문 구조 (잠정)

Hybrid 구조 — *Method* 는 Stage 별, *Results* 는 Phase 별:

| Chapter | 제목 | 작성 가능 여부 | 비고 |
|---|---|---|---|
| 1 | Introduction | 작성 가능 | 본 보고서 §1 기반 |
| 2 | Related Work | 부분 가능 | PlanarSplatting/CityGSV2/ULSR-GS/AlignGS 비교, 추가 survey 필요 |
| 3 | Methodology | **작성 가능** (수식 확정) | 본 보고서 §3 기반 |
| 4 | Phase 1 — Mechanism Validation | **작성 가능** | 본 보고서 §4, 결과 6/6 통과 |
| 5 | Phase 2 — CityGML Quality Evaluation | **부분 가능** | 본 보고서 §5, *인터페이스 정렬 후 확정* |
| 6 | Phase 3 — Real Data Demonstration | 미착수 | Step 1 완료 후 진입 |
| 7 | Discussion | 부분 가능 | 본 보고서 §6 기반 |
| 8 | Conclusion | Phase 3 후 | |

**현재 작성 시 큰 위험 없는 chapter**: 1, 3, 4 (전체) + 5 의 Phase 1→2 전이 부분 + 7 (지금까지 발견 정리). 이 chapter 들은 *지금 초안 시작 가능*.

**Phase 2 결론 확정 후 작성**: 5 의 ablation 정량 비교 + 결론 + 6 + 8.

### 8.1 Contribution claim 잠정 (현재 입증된 범위)

박사 thesis 의 contribution 을 솔직하게 정리하면:

1. **(Framework)** 미분 가능 렌더링 + 의미론 + 도메인 규칙 + 구조 정합 의 통합 학습 framework — 두 수준 (intra/inter primitive) 의 공동 최적화 형식화
2. **(Mechanism)** L_mutual, L_structure 의 설계와 *primitive 수준* 효과 검증 (Phase 1+2)
3. **(CityGML)** 복잡 건물 (complex/hip/tri-slope) 에서 메커니즘 2 의 +10~17%p val3dity 개선 입증 (Phase 2, 잠정)
4. **(Pipeline)** Stage 2→3 인터페이스 정렬 — group 정보 보존 (Step 1 완료 후 추가)
5. **(Real data)** real UAV 데이터 + 순차 비교 (Phase 3 후 추가)

박사논문 strong claim 은 1+2+3+4 가 안정화된 후. 5 가 가장 큰 differentiating contribution 이지만 미착수.

---

## 9. 위험 요소 및 일정

### 9.1 일정 (잠정)

| 시점 | 마일스톤 |
|---|---|
| 2026-04-26 (현재) | 본 보고서 작성 |
| ~05-03 (1주) | Step 1 (인터페이스 정렬) + 진짜 천장 재측정 + C3 진단 완료 |
| ~05-10 (2주) | Phase 2 결론 확정, REPORT v5 작성 |
| ~06-초 (1개월) | Phase 3 진입, GauU-Scene 학습 + Stage 3 |
| ~07-초 (2개월) | Phase 3 결과 + 순차 비교 + 성수동 시연 |
| ~08-초 (3개월) | 박사논문 chapter 1, 3, 4 초안 |
| ~10-초 (5개월) | 박사논문 chapter 5, 6, 7 초안 |
| ~12-초 (7개월) | 박사논문 전체 초안 + 심사 준비 |

### 9.2 위험 요소 (솔직)

#### 위험 R1: 인터페이스 정렬 후에도 4 조건 차이 미미

**가능성**: 중간. C3 (L_normal_align 약효) 가 strong supervision 환경에서 본질적이라면, group 정보를 정직하게 받아도 메커니즘 2 의 효과가 작을 수 있음.

**대응**:
- Phase 2 결론을 "단순 건물에선 효과 없음, 복잡 건물에선 +10~17%p" 로 *type-conditional* 으로 보고
- thesis 의 main claim 을 "supervision 강도에 따라 메커니즘 2 의 효과 강도가 달라진다 — Phase 1 (PSNR 22) 강함, Phase 2 (PSNR 40+) 약함, Phase 3 (real, PSNR ~25-30) 중간 예상" 로 재정의
- Phase 3 (real UAV) 가 *오히려 thesis 를 더 잘 보여주는 환경* 일 수 있음 — 약점이 아닌 nuance

#### 위험 R2: Phase 3 시간 압박

**가능성**: 중간-높음. Phase 2 결론이 5월 중순까지 확정되어야 Phase 3 학습 + 평가 + 비교가 7월까지 끝남. 1주라도 늦어지면 박사논문 timeline 이 dominoes.

**대응**:
- Step 1 (인터페이스 정렬) 가 4-6 시간이라 빠르게 결판
- Phase 3 의 GauU-Scene 학습은 ckpt 이미 일부 완료 (기억 — 검증 필요)
- 성수동 학습은 Stage 1 완료 상태이므로 Stage 2 만 돌리면 됨 (5-7 시간/조건)

#### 위험 R3: 측정 인프라 fragility 가 더 있을 수 있음

**가능성**: 낮지만 0 아님. bbox 와 GT_convex 두 개의 1줄 단위 오류가 발견됐는데, Stage 3 에 비슷한 numerical edge case 가 더 숨어있을 가능성.

**대응**:
- 인프라 stress test 한 번 수행 — Stage 3 의 모든 numerical parameter 에 대해 sensitivity 측정
- 측정 인프라의 안정성 자체를 박사논문 contribution 의 일부로 (Reproducibility 단원)

#### 위험 R4: 박사 thesis 의 main claim 자체가 약화될 가능성

**가능성**: 낮음. 메커니즘 1 은 일관 작동, 메커니즘 2 도 복잡 건물에서 작동. 단 *전반적* claim ("공동 최적화 → CityGML 개선") 이 *type-conditional* 로 약화되면 thesis 의 강도 감소.

**대응**:
- thesis 를 더 *정직하게* 재정의 — "복잡 건물 + 약한 supervision 환경에서 효과 강함" 같이
- 약점이 발견된 부분은 *future work* 로 명시 (단순 건물 메커니즘, strong supervision 보완)
- contribution 의 단단한 부분 (framework, primitive level 검증, 인프라) 을 강조

### 9.3 의사결정이 필요한 지점

지도교수님께 의견 구하고 싶은 사안:

1. **Phase 2 의 type-conditional 결과 (단순 건물 회귀) 를 어떻게 해석/보고할지** — 약점인가 nuance 인가?
2. **GT_convex 같은 측정 인프라 오류 발견을 contribution 의 일부 (reproducibility) 로 강조할지** vs 단순히 정정만 할지?
3. **Phase 3 시작 전 Phase 2 결론을 얼마나 확정해야 하는지** — 인터페이스 정렬만 하고 진입 vs 진짜 천장까지 측정 후 진입?
4. **박사논문 작성 시작 시점** — Phase 3 결과 기다림 vs 작성 가능한 chapter (1, 3, 4) 부터 병행?
5. **시너지 부재 (Both ≤ Structure)** 의 의미 — 메커니즘 설계의 한계인가, 아니면 측정 환경의 artifact 인가?

---

**보고 끝.** 본 문서의 데이터 출처는 `results/phase1_ablation/REPORT.md` (Phase 1) 와 `results/phase2_ablation_citygml/REPORT.md` (Phase 2 v4) 에 있으며, 코드는 `src/stage1`, `src/stage2`, `src/stage3` 모듈에 있습니다.

문의 / 보강 요청은 본 문서에 직접 코멘트 부탁드립니다.

---

## 부록 A. PDF 변환 방법

본 markdown 을 PDF (그림 포함) 로 만드는 3 가지 방법:

### A.1 VS Code 확장 (가장 쉬움, 권장)

1. VS Code 에서 `Markdown PDF` 확장 설치 (yzane.markdown-pdf)
2. `docs/REPORT_FOR_ADVISOR.md` 파일 열고 우클릭 → "Markdown PDF: Export (pdf)"
3. 같은 디렉토리에 PDF 생성

**장점**: 한글 폰트 자동 처리, 그림 자동 포함, 수식 (KaTeX) 렌더링.
**주의**: 수식이 안 나오면 확장 설정에서 `markdown-pdf.executablePath` 또는 `markdown-pdf.styles` 확인.

### A.2 pandoc (CLI, 호스트에 pandoc + LaTeX 설치 필요)

```bash
sudo apt install pandoc texlive-xetex texlive-fonts-extra fonts-nanum
cd docs
pandoc REPORT_FOR_ADVISOR.md \
  -o REPORT_FOR_ADVISOR.pdf \
  --pdf-engine=xelatex \
  -V mainfont="NanumGothic" \
  -V CJKmainfont="NanumGothic" \
  -V geometry:margin=2cm \
  --resource-path=.:..
```

**장점**: 명령 한 줄, 재현 가능.
**주의**: LaTeX 설치 필요 (~2GB). 한글 폰트 (NanumGothic) 설치 필요.

### A.3 브라우저 print (그림 보장, 가장 단순)

1. VS Code 의 markdown preview (Ctrl+Shift+V) 로 미리보기 열기
2. 또는 browser-friendly markdown viewer (예: [markdown.land/](https://markdown.land/) 같은 사이트에 내용 붙여넣기 — 단 외부 업로드 시 보안 주의)
3. 브라우저에서 Ctrl+P → "PDF 로 저장"

**장점**: 별도 도구 설치 불필요.
**주의**: 그림 경로가 상대 경로 (`../results/...`) 이므로 브라우저가 못 찾을 수 있음 → 절대 경로로 변환 필요.

### A.4 추천

**A.1 (VS Code Markdown PDF)** 이 한글 + 그림 + 수식 모두 한 번에 처리하므로 가장 무난. 설치 1 분, 변환 30 초.
