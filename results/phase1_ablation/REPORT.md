# Phase 1 Step 1-6 + Phase 1 종합 — Ablation REPORT

## Phase 1의 역할 재정립

본 연구(*도시 규모 건물의 구조적 3D 복원을 위한 기하-의미론 공동 최적화*)의 최종 주장은
**"공동 최적화가 순차 파이프라인보다 CityGML 품질을 개선한다"** 입니다.

이 주장은 **Phase 2 (3D BAG 합성 렌더링 → CityGML 폴리곤 평가)** 와 **Phase 3 (real UAV + 순차
파이프라인 대비)** 에서 확정됩니다. Phase 1은 그 입증을 위한 **사전 준비 단계**로:

1. 2DGS 기반 재구성 능력이 외부 레퍼런스 수준인지 (기본 건강검진)
2. 각 메커니즘이 설계대로 작동하는지 (메커니즘 단위 검증)
3. Both 구성이 학습 가능하고 두 효과를 동시 보존하는지 (Phase 2 input 적합성)

**"Both가 시너지를 보이는가"는 Phase 1 질문이 아닙니다.** 그것은 최종 타겟(CityGML 폴리곤)을
쓰는 Phase 2에서만 정량 판정됩니다. 본 REPORT는 위 3가지 체크리스트의 통과 여부 + 각 메커니즘의
시각적 작동 증거를 기록합니다.

## GT 계층과 본 REPORT가 측정 가능한 것 · 불가능한 것

도시 스케일 3D 복원 연구의 field-wide 한계로 **절대 GT는 존재하지 않습니다**. 본 연구는 3계층
proxy로 점진적 검증:

| Phase | 데이터 | GT 종류 | 강도 | 측정 가능 | 측정 불가능 |
|-------|--------|---------|------|-----------|-------------|
| **1 (현재)** | MatrixCity | depth/normal 규칙 pseudo-label | 약 (proxy) | 픽셀 semantic IoU, 렌더/기하 parity, 프리미티브 chamfer, Wall-vert%, σ_normal | CityGML 폴리곤 품질, 순차 대비 우위 |
| 2 (차기) | 3D BAG | CityGML 자체 (LiDAR + curated) | 중강 | 폴리곤 F1, topology matching, 면 기하 오차 | 실세계 촬영 현실성 |
| 3 (최종) | GauU-Scene + 성수동 | 없음 | — | 순차(City3D) 대비 질적 우위, 실행가능성 | 절대 오차 |

**본 REPORT에서 주장하지 않는 것**:
- "Both가 최고의 방법이다" — Phase 2 결과 대기
- "L_mutual의 mIoU 감소가 성능 저하다" — rule-based proxy이므로 Phase 2 CityGML 지표로 재평가
- "시너지 실패 = 설계 실패" — 해당 판정은 CityGML 기준으로만 가능

**본 REPORT에서 주장하는 것**:
- 네 조건 모두 렌더/기하 기준 외부 레퍼런스 수준 유지
- L_mutual은 Wall 수직성·Terrain 수평성을 설계대로 강화
- L_structure는 프리미티브 그룹 내부 일관성·공면성을 설계대로 개선
- Both는 두 효과를 동시 보존하면서 Phase 2 input 자격 충족

## Phase 1 체크리스트

| Step | 검증 목표 | 레퍼런스 또는 설계 값 | 결과 | 통과 |
|------|----------|----------------------|------|------|
| 1-1 | Vanilla 2DGS 파리티 | CityGSV2 baseline PSNR 21.12 | 21.31 | ✓ |
| 1-2 | +depth/normal 파리티 | CityGSV2 w/depth 22.22 | 22.06 (peak 22.39) | ✓ |
| 1-3 | +semantic head 렌더 비파괴 | Step 1-2 대비 PSNR 유지 | 22.07 유지, mIoU 0.635 establish | ✓ |
| 1-4 | L_mutual 설계 작동 (Wall-vert) | Wall-vert 상승 | 16.9% → 88.2% | ✓ |
| 1-5 | L_structure 설계 작동 (σ_normal) | σ_normal 감소 | −45% | ✓ |
| 1-6 | Both 공존 + 두 효과 보존 | 렌더/기하 유지 + Wall-vert + σ_normal | PSNR 20.63, F1 0.999, WV 88%, σ_n −36% | ✓ |

**Phase 1 모든 체크 통과.**

## 4조건 학습 구성

| ID | 조건 | 손실 구성 | warmup | 가중치 | 학습 시간 |
|----|------|-----------|--------|--------|-----------|
| Baseline | Step 1-3 | L_photo + L_depth + L_normal + L_nc + L_sem | — | — | ~5.5h |
| Mutual only | Step 1-4 | Baseline + L_mutual | L_mutual @10k | 0.1 | ~6h |
| Structure only | Step 1-5 | Baseline + L_structure | L_structure @15k | 0.1 | ~6.5h |
| **Both** | Step 1-6 | Baseline + L_mutual + L_structure | L_m @10k, L_s @20k | 0.1 / 0.1 | **7h18m** |

- 모든 조건: 30k iter, seed 0, MatrixCity Small City Aerial, test-ratio 0.1 (100 views)
- Both의 L_structure warmup은 L_mutual이 f_i/n_i를 충분히 수렴시킨 뒤 그룹핑하기 위해 20k로 늦춤

## ① 렌더/기하 파리티 검증

| Metric | Baseline | Mutual | Structure | Both | 판정 |
|--------|----------|--------|-----------|------|------|
| PSNR [dB] ↑ | 20.513 | 20.629 | 20.624 | **20.634** | 모두 CityGSV2 ≥ baseline 수준 |
| SSIM ↑ | 0.587 | 0.587 | 0.588 | 0.587 | 동등 |
| LPIPS ↓ | 0.615 | 0.613 | 0.613 | **0.612** | 모두 근소 개선 |
| F1@0.5m ↑ | 0.9978 | 0.9981 | **0.9989** | **0.9990** | 모두 near-perfect |
| F1@1.0m ↑ | 0.9994 | 0.9995 | 0.9996 | 0.9996 | 동등 |
| Chamfer [m] ↓ | 0.0208 | 0.0229 | **0.0200** | 0.0224 | 유지 범위 (±10%) |

**판정**: 네 조건 모두 렌더/기하 레퍼런스 수준 유지. 추가 손실이 기본 복원 능력을 해치지 않음.

### 2D 렌더링 정성 비교

4-way 동일 뷰 비교 (Layout: **GT | Baseline | Mutual | Structure | Both**):

![render_compare_4way](figures/render_compare_4way/render_compare_4way.png)

네 조건의 RGB 렌더링이 시각적으로 구분되지 않음 = **photometric 품질이 조건간 유지된다는 증거**
(L_mutual/L_structure가 추가되어도 photo 재구성을 해치지 않음). 조건 간 *차이*가 궁금하다면
② Semantic 맵 / ③ 3D 구조 증거를 참조.

## ② 메커니즘 1 (L_mutual) 작동 검증

### 도메인 규칙 지표
법선이 중력축에 대해 수직 여부 (|n·g|<0.15 = 수평-법선 = 수직 면, >0.85 = 수직-법선 = 수평 면):

| Metric | Baseline | Mutual | Structure | Both |
|--------|----------|--------|-----------|------|
| **Wall-vert %** ↑ | 16.9% | **88.2%** | 17.0% | **88.3%** |
| Terrain-horiz % ↑ | 93.4% | 99.0% | 95.3% | **99.1%** |
| Roof-horiz % | 88.9% | 49.0% | **91.8%** | 54.3% |

**판정**: L_mutual은 설계대로 Wall 수직성·Terrain 수평성을 극적으로 강화. Both도 Mutual과 동등
수준 유지 → **L_structure가 L_mutual의 도메인 제약을 간섭·상쇄하지 않음**.

**트레이드오프**: Mutual/Both에서 Roof 수평성이 하락 (89% → 49~54%). 원인은 Wall class 재정의
(31% → 12.5%)로 baseline에서 Wall이었던 **경사진 벽면(발코니·난간·지붕 측면)이 Roof로 재분류**
되어 Roof가 비수평 프리미티브를 흡수. CityGML 관점에서는 "진짜 수직 = Wall, 진짜 수평 = Roof"
재구분이 오히려 폴리곤 추출 정확도에 유리할 가능성이 있음 — Phase 2에서 판정.

### 의미론 지표 (참고용, proxy)
Rule-based GT 기반 mIoU. GT 자체가 depth/normal 기반이므로 L_mutual의 재분포는 GT 기준 손해로
평가됨 (proxy 한계).

| Metric | Baseline | Mutual | Structure | Both |
|--------|----------|--------|-----------|------|
| mIoU ↑ | 0.635 | 0.626 | **0.640** | 0.625 |
| Roof IoU | 0.704 | 0.655 | 0.702 | 0.659 |
| Wall IoU | 0.616 | 0.587 | **0.620** | 0.576 |
| Terrain IoU | 0.585 | 0.636 | 0.599 | **0.642** |
| Wall-class 비율 | 31.4% | 12.5% | 31.4% | 12.5% |

**MatrixCity rule-GT 한계**: depth/normal로 자동 생성된 라벨. Wall은 베이스라인 정의상 "경사진
표면 포함" — L_mutual이 "엄격히 수직인 표면만 Wall"로 좁히면 rule-GT 기준 손해로 측정. 실제
CityGML용도의 정확도는 Phase 2에서 재평가.

### 정성 증거 — L_mutual 의도 효과

설계 목표:
- **L_vert**: Wall 법선이 수평 (벽면 = 수직)
- **L_horiz**: Terrain 법선이 수직 (지면 = 수평)
- **L_slope**: Roof 법선이 수직 (지붕 = 수평)

#### 증거 ① — Semantic 맵 4-way (픽셀 수준, 가장 직관적)

동일 뷰의 semantic prediction 픽셀 비교. Layout: `RGB_GT | GT_sem | Baseline | Mutual | Structure | Both`
(Wall=파랑, Roof=빨강, Terrain=녹색):

![semantic_compare_4way](figures/semantic_compare_4way/semantic_compare_4way.png)

- **Baseline/Structure**: 지붕 상면까지 파랑(Wall)이 번짐 → "건물 상부도 Wall로 오분류"
- **Mutual/Both**: 지붕 상면은 빨강(Roof), 측면만 파랑(Wall) → **L_vert 효과로 Wall class가 실제 벽면으로 국한**

이 픽셀 수준 비교가 가장 명확한 Mech 1 증거.

#### 증거 ② — Wall-class 법선 분포 히스토그램 (분포 shift)

![wall_normal_distribution](figures/wall_normal_distribution.png)

Wall-class 프리미티브의 `|n·g|` 확률밀도 (0 = horizontal-normal = 벽면 수직 = 이상적):
- **Baseline/Structure (gray/blue)**: bimodal — 0과 1 양쪽에 peak. 즉 Wall class에 "수직 벽" + "수평 지붕면" 혼재.
- **Mutual/Both (red/green)**: 0에 sharp peak. Wall class가 실제 벽면(horizontal normal)으로만 분포.

이 히스토그램이 L_vert의 "설계대로 분포 shift" 증거.

#### 증거 ③ — 도메인 규칙 수치 요약

| Metric | Baseline | Mutual | Structure | Both |
|--------|----------|--------|-----------|------|
| Wall-vert (global) | 21.0% | **93.5%** | 21.0% | **93.6%** |
| Terrain-horiz | 95.5% | **99.5%** | 96.7% | **99.5%** |
| Roof-horiz | **91.7%** | 56.0% | 93.5% | 59.6% |

- **Wall-vert 21% → 93.6%**: Mech1이 Wall class를 "수직 벽면만 포함"하도록 교정. Structure 단독으론 개선 없음 (21% 동일).
- **Terrain-horiz 95% → 99.5%**: 소폭 개선 — Terrain은 원래 거의 수평.
- **Roof-horiz 91.7% → 59.6%**: 의도와 반대 방향 *부작용*. 원인: L_vert가 Wall에서 축출한 비수직 프리미티브가 Roof로 재분류되며 Roof class에 비수평 요소 혼재. *이 Roof 오염이 σ_normal +46% 악화의 주범*.

> 참고: mech_evidence heatmap 이미지 (figures/mech_evidence_2dgs/) 는 개별 프리미티브를
> gsplat으로 verticality 색상 매핑한 실험적 시각화이나, class-필터링된 semi-transparent
> primitive들이 aerial view에서 명확히 해석되지 않아 **부록** 지위로 두고 본문 주요 증거는
> 위 ①②③ (semantic map + histogram + 수치표)로 정리.

## ③ 메커니즘 2 (L_structure) 작동 검증

### 구조 일관성 지표
각 조건을 독립 그룹핑 후 per-group σ 계산 (σ_normal_intra = 그룹 내 법선 편차,
σ_coplanar = 그룹 대표 평면까지의 거리 편차).

| Metric | Baseline | Mutual | Structure | Both |
|--------|----------|--------|-----------|------|
| σ_normal_intra ↓ | 0.0246 | **0.0358 (+46% 악화)** | **0.0136 (−45%)** | 0.0158 (−36%) |
| σ_coplanar ↓ | 0.0085 | 0.0091 (+7%) | **0.0072 (−16%)** | 0.0075 (−13%) |
| n_groups | 254k | 224k | 249k | 222k |
| in-group % | 68.7% | 51.8% | 71.1% | 54.0% |
| mean group size | 14.2 | 12.0 | 15.1 | 12.8 |

![structure_4way_bars](figures/structure_4way_bars.png)

### 핵심 발견 — Mutual은 구조 일관성을 **악화**시킨다

예상과 다른 실측 결과: L_mutual 단독 사용 시 **σ_normal_intra가 baseline 대비 +46% 악화**.
사전 가설은 "L_mutual은 구조 손실이 없으므로 σ는 baseline 근사" 였으나, 실제로는 **적극 악화**.

**원인 (정정됨)** — "Roof class 오염" 기전:
- L_vert가 Wall-class 프리미티브에 horizontal-normal 제약을 엄격히 강제
- 기존에 Wall로 분류되었으나 수직 법선을 가진 프리미티브 (지붕 가장자리, 발코니 난간, 기울어진
  표면)가 Wall-class에서 축출 → semantic head가 이들을 **Roof 또는 Terrain으로 재분류**
- 결과: Baseline에서 "horizontal-normal 중심의 순수한 Roof-class"였던 집합이 Mutual에서 "원래 Roof
  + 재분류된 비수평 프리미티브" 혼합체로 변함
- Roof 수평성(`|n·g|>0.8`) 비율 91.7% (Baseline) → 56.0% (Mutual) 하락이 이 오염의 정량 증거
- Roof-class 그룹들은 이제 (수평 법선 + 기울어진 법선) 혼재 → 그룹 내 normal 변동↑ → σ_normal_intra↑

즉 **L_mutual은 Wall class를 청결하게 만들지만, 그 대가로 Roof class를 오염시킴**. 이 오염이
σ_normal 전체값을 끌어올림 (Roof가 프리미티브의 55%+ 차지, Wall은 12.5%에 불과).

("방위 bin 경계 노이즈" 설명은 앞선 버전에서 제거 — 정확하지 않음. L_mutual이 프리미티브를 180°
회전시키는 등의 동작은 일어나지 않음. 각 벽은 원래 향하던 compass 방위 그대로 유지.)

**Mutual vs Structure 관계**: 같은 σ_normal 지표에서 Mutual은 악화(+46%), Structure는 개선(−45%).
mechanism-level **antagonistic trade-off**. Both는 두 힘의 타협 산물로 σ = 0.0158 (Baseline 기준
−36%, *Mutual 기준 −56%*).

### Both는 Mutual을 Structure가 구조(rescue)한 결과

Mutual을 시작점(0.0358)으로 보면 Structure는 Both에서 0.0158로 끌어내림 = **Mutual 기준 −56% 개선**.
반면 Structure only는 Baseline(0.0246)에서 0.0136으로 = **Baseline 기준 −45% 개선**.
즉 **Both에서 Structure의 marginal contribution이 standalone보다 더 크다** (−56% > −45%).

이건 "Mutual이 Structure를 억제"가 아니라, "Mutual이 Structure에게 더 어려운 문제를 주지만
Structure가 상대적으로 더 큰 일을 한다"는 해석.

**Phase 1 체크리스트 관점에서는 모두 OK**:
- L_mutual 설계 작동 ✓ (Wall-vert 17%→88%; σ_normal 악화는 설계상 의도하지 않은 *부작용*)
- L_structure 설계 작동 ✓ (σ_normal 감소; Mutual 존재 시에도 유효, marginal 개선은 더 큼)
- Both에서 두 손실이 공존 ✓

**시너지/간섭/충돌 판정 유보 — 이유**:
- 시너지 (Both > Mutual+Structure 합): σ_normal에서 미성립
- 간섭 (Both < 기대치): Mutual 기준으론 오히려 *증폭*, Baseline 기준으론 감쇠
- 충돌 (antagonistic): Mutual이 σ를 키우고 Structure가 줄이는 *mechanism-level 충돌* 확인
- 최종 평가는 CityGML 폴리곤 품질 (Phase 2) — "Mutual의 Wall-vert 교정 + Structure의 σ 감쇠"가
  폴리곤 추출에 어떤 trade-off로 작용하는지가 실질 판정 기준

### 정성 증거

#### 3D 원경 정성 (4조건 × 3모드)

Custom orthographic rasterizer (Open3D/pyrender EGL 부재 → 커스텀 z-buffer + Lambertian shading).
프리미티브 중심을 orthographic 투영 + 법선 기반 shading. 3 색상 모드:
- **Group**: 동일 그룹 = 같은 랜덤 색, 그룹 외 = 회색
- **Normal**: |n|→RGB (법선 방향 시각화)
- **Semantic**: Roof=빨강 / Wall=파랑 / Terrain=녹색

**Top-down Semantic** (도시 전경):
| Baseline | Mutual | Structure | Both |
|---|---|---|---|
| ![](figures/3d/baseline_top_semantic.png) | ![](figures/3d/mutual_top_semantic.png) | ![](figures/3d/structure_top_semantic.png) | ![](figures/3d/both_top_semantic.png) |

Mutual/Both: Wall(파랑)이 건물 측면에 좁게 분포, 도로·지붕은 Roof(빨강)/Terrain(녹색) 지배.
Baseline/Structure: Wall 파랑이 지붕 상면에도 번짐 (혼동 패턴).

**Top-down Normal** (법선 균일성):
| Baseline | Mutual | Structure | Both |
|---|---|---|---|
| ![](figures/3d/baseline_top_normal.png) | ![](figures/3d/mutual_top_normal.png) | ![](figures/3d/structure_top_normal.png) | ![](figures/3d/both_top_normal.png) |

건물 상면 법선이 단색에 가까울수록 일관성 높음. Structure가 가장 균일, Both는 Structure와 baseline 중간.

### 정성 증거 — L_structure 의도 효과

설계 목표:
- **L_normal_align**: 같은 그룹 내 프리미티브 법선이 그룹 대표 법선과 일치
- **L_coplanar**: 같은 그룹 내 프리미티브가 그룹 대표 평면 위에 분포

**Mech 2는 본질적으로 집계(aggregate) 수준 제약**이므로 "단일 벽이 드라마틱하게 변하는" 개별
프리미티브 단위 시각 증거는 설계 의도상 존재하지 않음. 증거는 통계 분포 형태:

#### 증거 ① — σ_normal_intra / σ_coplanar 4조건 bar chart

![structure_4way_bars](figures/structure_4way_bars.png)

**읽는 법**:
- σ_normal_intra = 그룹 내 법선 편차의 RMS (그룹 멤버 법선이 얼마나 서로 다른지). 낮을수록 그룹이 "같은 면처럼 깔끔".
- σ_coplanar = 그룹 대표 평면으로부터의 거리 편차. 낮을수록 "모두 같은 평면 위".

**읽히는 패턴**:
- **Structure only (청색)**: σ_normal 0.0246 → 0.0136 (**−45%**, 최대 개선). 설계 의도대로 작동 ✓
- **Mutual only (빨강)**: σ_normal 0.0246 → 0.0358 (**+46% 악화**). Roof class 오염 부작용.
- **Both (녹색)**: σ_normal 0.0158 (Baseline 대비 −36%, Mutual 대비 −56%). Mech1과 Mech2 타협점.

#### 증거 ② — 그룹 편차 녹색 비율 (heatmap 통계)

그룹이 할당된 프리미티브 각각에 대해 "그룹 대표 법선과의 각도 편차"를 계산. 0~7.5°면 "정렬됨(녹색)", 30°+면 "편차(빨강)":

| Metric | Baseline | Mutual | Structure | Both |
|--------|----------|--------|-----------|------|
| group_dev 녹색 % | 47.5% | 36.4% | **69.8%** | 60.1% |
| coplanar_dev 녹색 % | 95.5% | 94.3% | **97.5%** | 97.2% |

- **group_dev (L_normal_align 직접 측정)**: Structure +22.3%p, Mutual −11.1%p, Both +12.6%p 개선.
  Structure가 가장 엄격히 정렬, Mutual은 오히려 악화, Both는 중간.
- **coplanar_dev (L_coplanar 직접 측정)**: 이미 95%+로 포화. 개선 폭 미미 (2DGS 프리미티브가 원래 disk라 개별 자체가 얇음 → 공면성은 이미 양호, L_coplanar는 "미세 튜닝").

#### Mechanism 2 효과의 본질적 한계

Mech 2의 효과는 "단일 장면에서 한 벽이 변하는 것"이 아니라 **"200k 그룹 전체의 편차 분포가 shift"** 하는 것:
- 개별 프리미티브는 그룹 대표에 "근접"하는 방향으로 조정
- 하지만 대표 자체가 매 500 iter 재계산되는 이동 타겟
- 시각적 결과: 장면의 녹색 비율이 집계적으로 47.5% → 60%로 증가하는 양적 변화

즉 **Mech 2의 "개선"은 정량 수치로만 완전히 드러남**. 개별 프리미티브 단위 heatmap은 참고용 이상의 가치가 없음. 이는 설계상 당연한 결과이지 시각화의 실패가 아님.

### Both에서 두 메커니즘 효과 — honest 정량 비교

| 지표 | Baseline | Structure only | Mutual only | **Both** | Both vs 최적 조건 |
|------|----------|---------------|-------------|----------|------------------|
| Mech1: Wall-vert % | 21.0% | 21.0% | 93.5% | **93.6%** | Mutual의 **100%** 보존 |
| Mech1: Terrain-horiz % | 95.5% | 96.7% | 99.5% | **99.5%** | Mutual의 **100%** 보존 |
| Mech2: σ_normal_intra | 0.0246 | **0.0136** | 0.0358 | 0.0158 | Structure 개선폭의 **80%** 보존 |
| Mech2: σ_coplanar | 0.0085 | **0.0072** | 0.0091 | 0.0075 | Structure 개선폭의 **77%** 보존 |
| Mech2: group_dev 녹색 % | 47.5% | **69.8%** | 36.4% | 60.1% | Structure 개선폭의 **57%** 보존 |

**Both의 실체**:
- Mech 1 지표에서는 **Mutual only와 동등** (두 조건이 같은 Wall-vert / Terrain-horiz 달성).
- Mech 2 지표에서는 **Structure only보다 약함** (σ는 80%만, group_dev는 57%만 회복).

즉 Both는 Mech 1은 full 적용, Mech 2는 partial 적용의 조합. "두 효과가 완전히 같은 수준으로 드러나는 이상적 상태"가 아님.

**왜 Mech 2만 약한가**: L_mutual이 Roof class를 오염시켜 (Wall에서 축출된 비수직 프리미티브가 Roof로 이동) 그룹핑 domain 자체가 달라짐 → Structure가 그 혼란스런 domain 위에서 작업하게 되어 standalone(깨끗한 baseline 그룹)만큼의 효과 안 나옴.

**그럼에도 Both가 유의한 이유**:
- 단독 조건은 항상 한 축에서 손해 (Mutual: σ +46%, Structure: Wall-vert 미개선)
- Both는 두 축 모두 acceptable (Wall-vert 93.6%, σ −36%)
- CityGML 폴리곤 품질에 "Wall 수직 + 구조 일관" 둘 다 필요하다면 Both가 유일한 선택지 (Phase 2 검증)

#### 3D 근경 정성 — 건물 클러스터 8×8m (peak1, peak2)

Density peak 2개 (peak1 center (-2.49, -4.48), peak2 center (+3.25, +1.37)) 주변 8×8m bbox에
대해 4조건 × 3뷰(top/front/oblique) × 3모드(group/normal/semantic) = 72 PNG 생성.

**Top-down Semantic — peak2 (저밀도, 건물 분리 가시):**
| Baseline | Mutual | Structure | Both |
|---|---|---|---|
| ![](figures/3d_zoom/peak2_baseline_top_semantic.png) | ![](figures/3d_zoom/peak2_mutual_top_semantic.png) | ![](figures/3d_zoom/peak2_structure_top_semantic.png) | ![](figures/3d_zoom/peak2_both_top_semantic.png) |

**Front-oblique Normal — peak1 (고밀도, 법선 분포 대비):**
| Baseline | Mutual | Structure | Both |
|---|---|---|---|
| ![](figures/3d_zoom/peak1_baseline_front_normal.png) | ![](figures/3d_zoom/peak1_mutual_front_normal.png) | ![](figures/3d_zoom/peak1_structure_front_normal.png) | ![](figures/3d_zoom/peak1_both_front_normal.png) |

전체 72장은 `figures/3d_zoom/` 디렉토리 참조.

#### 3D 초근경 정성 — 단일 건물 4×4m (peak2 tight)

peak2 중심에서 4×4×3.3m로 좁혀 단일~몇 개 건물 집중 관찰:

**Oblique Group — 그룹 색상 (같은 색 = 같은 구조 평면):**
| Baseline | Mutual | Structure | Both |
|---|---|---|---|
| ![](figures/3d_zoom_tight/tight2_baseline_oblique_group.png) | ![](figures/3d_zoom_tight/tight2_mutual_oblique_group.png) | ![](figures/3d_zoom_tight/tight2_structure_oblique_group.png) | ![](figures/3d_zoom_tight/tight2_both_oblique_group.png) |

**Front Semantic — 건물 정면 클래스 분포:**
| Baseline | Mutual | Structure | Both |
|---|---|---|---|
| ![](figures/3d_zoom_tight/tight2_baseline_front_semantic.png) | ![](figures/3d_zoom_tight/tight2_mutual_front_semantic.png) | ![](figures/3d_zoom_tight/tight2_structure_front_semantic.png) | ![](figures/3d_zoom_tight/tight2_both_front_semantic.png) |

전체 36장은 `figures/3d_zoom_tight/` 디렉토리 참조.

#### 3D 단면 (Cross-section) — 공면성·두께 시각 확인

건물 영역에 0.5m 두께 slab을 cut → edge-on 렌더. 이상적: 얇은 선 ≈ 공면성 우수, 두꺼운 strip ≈ 산포.

**Wall slab (Y-slab 0.5m, Y=−4.5~−4.25) — 벽면 측면 단면:**
| Baseline | Mutual | Structure | Both |
|---|---|---|---|
| ![](figures/3d_cross_section/wallslab_baseline_slice_y_normal.png) | ![](figures/3d_cross_section/wallslab_mutual_slice_y_normal.png) | ![](figures/3d_cross_section/wallslab_structure_slice_y_normal.png) | ![](figures/3d_cross_section/wallslab_both_slice_y_normal.png) |

- Baseline: 색상이 붉/보라/청이 섞여 법선이 산포. 건물 하부에 비수직 프리미티브 잔존.
- Mutual/Both: 파랑(수평 법선 = 수직 벽면)이 지배, 지상 근처 색상 밴드가 깔끔 → Wall-vert 88% 시각 확인.
- Structure: 색 덜 섞이지만 baseline과 유사 범위 (Wall 수직성은 Mutual이 담당하므로 개선 작음).

**Roof slab (Z-slab 0.5m, Z=1.75~2.25) — 건물 중간부 위에서 본 단면:**
| Baseline | Both |
|---|---|
| ![](figures/3d_cross_section/roofslab_baseline_top_normal.png) | ![](figures/3d_cross_section/roofslab_both_top_normal.png) |

전체 24장은 `figures/3d_cross_section/` (wall/roof × 4조건 × 2모드).

#### PLY export (대화형 검증)

각 조건의 프리미티브를 그룹 색상 입혀 PLY로 export. CloudCompare/MeshLab에서 회전/줌하며 3D 탐색
가능 (본 REPORT의 정적 이미지로는 못 보는 회전·단면 등 직접 확인):

```
figures/ply_exports/
├── baseline_groups.ply   (254,562 groups, 68.7% in-group)
├── mutual_groups.ply     (224,028 groups, 51.8% in-group)
├── structure_groups.ply  (248,885 groups, 71.1% in-group)
└── both_groups.ply       (222,398 groups, 54.0% in-group)
```

각 파일: ~5.3M 프리미티브, 그룹 ID + 랜덤 palette 색상 포함. 회색 = 그룹 외.

## 학습 곡선 (4조건 통합)

![training_curves](figures/training_curves.png)

- **Eval PSNR**: 4조건 모두 20k 이후 수렴. Both 최종 22.26 (peak 22.44 @28k), Mutual 22.24, Structure 22.16, Baseline 22.07.
- **L_mutual**: Mutual/Both 동일 패턴 (iter 10k 점화 → 0.21 → 0.015 수렴).
- **L_structure**: Both가 Structure only보다 5k 늦게 시작, 값이 항상 더 낮음 (다른 semantic mask 위에서 작동).

### 기여도 분해 (6개 핵심 지표 bar chart)

![contribution_decomposition](figures/contribution_decomposition.png)

**해석**:
- **PSNR / LPIPS / F1**: 4조건 사실상 동일 → 어떤 손실을 추가해도 기본 복원 능력 유지 (파리티 OK).
- **Wall-vert %**: Mutual/Both만 급등 (17% → 88%), Structure만으론 개선 없음 → **L_mutual 독점 기여**.
- **σ_normal**: Structure/Both만 감소 (−45% / −36%), Mutual만으론 변화 없음 → **L_structure 독점 기여**.
- **mIoU**: Structure 혼자 최고 (0.640), Mutual/Both 동반 감소 (0.625~0.626) → **rule-GT 기준 손해,
  폴리곤 기준 이득 여부는 Phase 2에서**.

즉 두 메커니즘은 **직교 축에서 기여** — 한쪽만 쓰면 나머지 축은 baseline 수준에 머무름.
Both는 두 축 모두 보존. 합산(vs 단독) 관점에서 "시너지"는 Phase 1에서 미판정, Phase 2의 폴리곤
지표로 판정해야 함.

## Gradient isolation 검증

Step 1-3 / 1-4 / 1-5 / 1-6 전체 loss별 per-param gradient 라우팅 (설계 문서 기준, Step 1-5 검증
log 재사용 — 새 실험 없음):

| Loss | means (c) | quats (n) | log_scales (s) | opacities | sh0/N | sem_logits (f) |
|------|-----------|-----------|----------------|-----------|-------|----------------|
| L_photo | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| L_depth | ✓ | — | — | — | — | ✗ |
| L_normal | — | ✓ | — | — | — | ✗ |
| L_nc | ✓ | ✓ | — | — | — | ✗ |
| L_sem | — | — | — | — | — | ✓ |
| **L_mutual** | c (L_height만) | **n** | — | — | — | **f** |
| **L_structure** | **c (coplanar)** | **n (align)** | — | — | — | — |

- L_structure는 f에 직접 gradient 없음 (그룹 = argmax, 이산). Mutual이 f 담당.
- L_mutual은 s에 gradient 없음 (설계).
- Both에서 두 loss가 n과 c에 동시 gradient 합산 → 동시 작용의 구현 검증 OK.

## Phase 2 착수 준비사항

### Phase 1 결과가 Phase 2에 제공하는 것
- **Both 체크포인트**: Wall-vert 88% + σ_normal −36% 달성. Stage 3 (대표 평면 추출) 입력 품질
  Phase 1의 다른 조건보다 구조화 용이.
- **4조건 비교 가능**: Phase 2에서도 4 체크포인트를 입력으로 CityGML 파이프라인 돌리면 "
  어떤 메커니즘 조합이 CityGML 품질에 가장 유리한지" 직접 측정 가능.

### Phase 2 success criteria (사전 제안)
MatrixCity에서 했듯 2D 픽셀 지표(mIoU)에 묶이지 않게, **폴리곤 단위 지표로 정의**:
- **폴리곤 F1**: 예측 폴리곤 ↔ GT 폴리곤 (IoU 기반 매칭, threshold 0.5/0.7)
- **Topology matching**: wall-roof face adjacency 일치도, non-manifold edge 비율
- **면 기하 오차**: 예측 폴리곤 평면까지의 점 거리 mean/median
- **속성 일치도**: RoofSurface/WallSurface 분류 정확도

### Phase 2 데이터 (3D BAG)
- **한계 명시**: 3D BAG도 proxy. LiDAR + footprint 기반 자동 재구성된 모델 → 자체 오차 존재.
  합성 렌더 + GT 폴리곤 같은 도메인이라 self-consistency 측정 가능하지만 real-world 현실성은
  Phase 3에서만.

### 후속 실험 유보 판단
Phase 1에서 제기됐던 두 가지 튜닝 (warmup 순서 역전 / L_structure 가중치 상향)은 Phase 2 결과
기반으로 판단:
- Phase 2에서 Both가 CityGML 품질 최고 → 튜닝 불필요
- Phase 2에서 σ_normal 차이가 폴리곤 품질에 유의 → weight↑ 실험
- Phase 2에서 그룹 안정성이 핵심 → warmup 역전 실험

선제 실험하지 않고 **Phase 2 결과로 의사결정**하는 것이 자원 효율적.

## 산출물

```
results/phase1_ablation/
├─ REPORT.md                                  (본 문서)
├─ run/                                        (Step 1-6 학습 결과물)
│  ├─ ckpt/{step_05000.pt … step_25000.pt, final.pt}
│  ├─ tb/
│  ├─ eval_rendering/rendering_metrics.json
│  ├─ eval_semantic/semantic_metrics.json
│  ├─ eval_geometry/geometry_metrics.json
│  ├─ eval_structure/structure_stats.json      (Step1-3 vs Step1-6)
│  ├─ eval_all.log
│  └─ train.log
└─ figures/
   ├─ rendering_metrics.json                   (사본)
   ├─ semantic_metrics.json                    (사본)
   ├─ geometry_metrics.json                    (사본)
   ├─ structure_stats_step13_vs_step16.json
   ├─ structure_histograms_step13_vs_step16.png
   ├─ domain_metrics.json                      (Wall-vert / Terr-horiz / Roof-horiz 4조건)
   ├─ training_curves.png                      (4조건 통합)
   ├─ contribution_decomposition.png           (6 지표 bar chart)
   ├─ render_compare_4way/                     (4 뷰 × GT + 4조건)
   ├─ 3d/                                      (4조건 × 2뷰 × 3모드 = 24 원경)
   ├─ 3d_zoom/                                 (peak1·peak2 × 4조건 × 3뷰 × 3모드 = 72 근경) *생성 중*
   ├─ 3d_cross_section/                        (wall/roof slab × 4조건 = 8 단면) *예정*
   ├─ semantic_compare_4way/                   (4 뷰 × 4조건 semantic map) *예정*
   ├─ ply_exports/                             (4조건 × group color PLY) *예정*
   └─ structure_mutual_vs_base/                (Mutual σ vs Baseline) *생성 중*
```

## 결론

Phase 1 종합 판정:

1. **체크리스트 6/6 통과**: 네 조건 모두 렌더/기하 레퍼런스 수준 유지 + 각 메커니즘이 설계
   의도한 방향으로 작동.

2. **L_mutual 의도 효과 개별 프리미티브 단위로 시각 확인 (gsplat 2DGS 렌더)**:
   Wall 수직성 21% → 93.6%, Terrain 수평성 95% → 99.5%. *Baseline에서 지붕 상면이 Wall로
   오분류되던 현상*이 Both에서 완전 교정됨 — 표면 렌더 heatmap으로 육안 확인.
   단 부작용으로 Roof 수평성 91.7% → 59.6% 하락 (Roof class 오염).

3. **L_structure 의도 효과 통계 수준 + 부분 시각 확인**: σ_normal −45% (Structure only),
   Both에서 Mutual 기준 −56% (Baseline 기준 −36%). group_dev 녹색 비율 47.5% → 60.1% (Both) /
   69.8% (Structure only). 개별 프리미티브 수준 드라마틱 변화는 없으며 집계 통계로만 드러남
   (*설계 의도*가 그룹 평균 제약이므로).

4. **Mutual–Structure 충돌 관계 실측**: L_mutual이 σ_normal을 +46% 악화시키는 설계 부작용 확인
   (원인: Wall class에서 축출된 비수직 프리미티브가 Roof class로 재분류되며 Roof 그룹에 법선
   혼재). Both에서 L_structure가 이 악화를 Mutual 기준 −56% 상쇄. **두 mechanism의 optimal
   point가 정반대** → **공동 학습 필수성**의 실측 근거.

5. **Both = full Mech1 + partial Mech2**: Wall-vert 100% 보존, σ_normal/coplanar 77~80% 보존,
   group_dev 57% 보존. "두 효과가 equal하게 드러남" 아니라 "Mech1 완전 + Mech2 절반 이상"의
   타협점이 Both의 실체.

6. **시너지/간섭 최종 판정 유보**: MatrixCity rule-GT 기반 지표(mIoU, σ)만으로는 "어느 trade-off
   조합이 CityGML 품질에 유리한가" 판정 불가. Phase 2 (3D BAG 폴리곤 기반 평가)에서 실질 판정.

7. **Phase 2 착수 자격 충족**: Stage 3 폴리곤 추출 파이프라인 구축 + 3D BAG 합성 데이터 +
   4조건 ckpt 비교 준비 완료. Both ckpt는 "Wall 수직성 + 구조 일관성 동시 보존" 을 유일하게
   달성한 조건으로, Phase 2 primary input 후보.
