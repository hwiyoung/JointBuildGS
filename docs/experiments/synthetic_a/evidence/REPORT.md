# Synthetic A: Stage 3 단독 검증 — 결과 보고

## 수행 일시
2026-03-28 (최종, roof type 6개 세분화)

## 목적

**질문: Stage 3 알고리즘이 어떤 유형/수준의 프리미티브 오류까지 유효한 CityGML LOD2를 생성할 수 있는가?**

이 결과로:
1. 각 프리미티브 속성의 **허용 범위** 확립
2. **가장 민감한 요인** 식별
3. **건물 유형별** 허용 범위 차이 파악
4. Stage 2의 최적화 목표를 수치로 설정

## 핵심 결론

1. **법선이 지배적 요인**: N10°에서 84%, N20°에서 47%. 나머지 요인은 최대 노이즈에서도 90%+.
2. **Roof type에 따라 허용 범위가 크게 다름**: N10°에서 flat 98% vs complex 74% (24%p 차이). 기존 연구(Deep Multimodal Fusion 2023: RMSE 1.8배 차이)와 일관.
3. **구조적 품질과 의미론적 정확성은 다른 요인에 지배적으로 반응**: 법선→val3dity, 분류→Semantic Acc. L_sem만으로는 구조적 품질 개선 불가 → L_mutual 필요.

## Stage 3 알고리즘: 2.5D Hybrid

```
입력: 프리미티브 (center, normal, area, semantic class)
  ↓
[1. 클러스터링] 법선 유사도 기반 면 그룹핑
  - signed cosine similarity로 반대편 벽 분리
  - trimmed mean으로 이상 법선 제거
  - 각 그룹 → 하나의 평면 방정식 (plane_normal, plane_d)
  ↓
[2. Footprint 추출] wall plane 교차 → 2D polygon
  - 각 wall의 법선을 XZ 평면에 투영 (비수직 벽 처리)
  - wall plane 쌍의 교차점 = footprint 꼭짓점
  - active range 필터로 유효한 교차점만 선택
  - boundary trace → closed polygon
  - 실패 시 convex hull fallback + make_valid (self-intersection 처리)
  ↓
[3. 2.5D Solid 구성]
  - Flat roof → footprint extrusion (ground → eaves 높이)
  - Gable → ridge line = 2개 roof plane의 교차선
  - Hip → straight skeleton에서 ridge 추출
  - Shed → 단일 경사면 extrusion
  - Eaves 높이 = roof-wall plane 교차에서 정확 계산
  ↓
[4. CityJSON 출력]
  - RoofSurface / WallSurface / GroundSurface 라벨 부여
  - 가장 아래 면을 GroundSurface로 강제 (누락 방지)
  - signed volume check → winding 보정
  - val3dity 검증 → 실패 시 convex polytope fallback
```

핵심 설계 원칙:
- **Footprint은 wall plane의 교차**로 계산 — 프리미티브 수/위치에 덜 의존
- **Eaves 높이는 roof-wall plane 교차**로 정확 계산 — 프리미티브 분포에 무관
- **Adaptive threshold** — 순서 통계량에 기반, 건물 크기와 무관

구현: `scripts/build_2_5d.py` (1,218줄), `scripts/building_to_citygml_v4.py` (1,017줄)

## 실험 설계

### 데이터
**3D BAG** (네덜란드 CityJSON LOD2.2, TU Delft). 3 scene: Amsterdam Jordaan / Rotterdam Center / Delft Residential.

### Roof type 분류 (GT에서 직접)
RoofSurface 면 수 + 법선 방향을 GT CityJSON에서 직접 읽기 (추정 아님):

| Roof type | 분류 기준 | 모집단 | 샘플 |
|-----------|---------|------|------|
| flat | RoofSurface 1개, 법선 수직 | 1,453 | 100 |
| shed | RoofSurface 1개, 법선 경사 | 11 | 10 |
| gable | RoofSurface 2개 | 1,564 | 100 |
| tri-slope | RoofSurface 3개 | 1,256 | 100 |
| hip | RoofSurface 4개 | 912 | 100 |
| complex | RoofSurface 5개+ | 2,148 | 100 |
| **합계** | | 7,344 | **510** |

기존 연구에서 건물 형태/roof type이 CityGML 생성 정확도에 유의미한 영향을 미치는 것이 확인됨 → 유형별 평가 필요:

- **Building3D (Wang et al., ICCV 2023)**: 160K+ 건물 벤치마크에서 전통적 방법(PolyFit)의 mesh IoU가 단순 건물 0.97 → 복잡 건물 0.36으로 **2.7배 하락** (Table 5). 딥러닝 방법에서도 entry-level(단순 지붕) F1=0.76 → Tallinn(복잡 도시) F1=0.66으로 **13%p 하락** (Table 3 vs 4). 건물 복잡도가 재구성 정확도의 주요 변동 요인임을 정량적으로 확인.
- **Deep Multimodal Fusion (Huang et al., Canadian J. Remote Sensing, 2023)**: 9개 지붕 유형별 LOD2 모델링에서 height RMSE가 1.02m(단순) ~ 1.86m(복잡)으로 **1.8배 차이**. 유형별 분류 정확도는 전체 97.58%이나 희소 유형(gambrel, dutch)에서 유의미하게 낮음.

### 노이즈 조건 (17개)
단일 14개 (법선 3 + 위치 2 + 분류 2 + 누락 2 + 아웃라이어 2 + 면적 3) + 복합 2개 (N10_worst, N2_worst).

## 결과

### 전체 결과 (510 건물)

| 조건 | val3dity | Chamfer (m) | Sem. Acc |
|------|:---:|:---:|:---:|
| **clean** | **100%** | 0.00 | 1.00 |
| normal_2° | 91% | 0.90 | 0.96 |
| **normal_10°** | **84%** | 1.59 | 0.93 |
| **normal_20°** | **47%** | 2.22 | 0.81 |
| pos_iso_0.5m | 97% | 0.97 | 0.97 |
| pos_iso_1.0m | 98% | 1.31 | 0.96 |
| cls_15% | 92% | 1.60 | **0.74** |
| cls_30% | 90% | 1.68 | **0.65** |
| missing_30% | 96% | 0.67 | 0.97 |
| missing_50% | 95% | 0.84 | 0.97 |
| outlier_5% | 95% | 1.53 | 0.93 |
| outlier_10% | 95% | 1.89 | 0.89 |
| area_30% | 99% | 0.12 | 1.00 |
| area_50% | 98% | 0.16 | 0.99 |
| area_100% | 97% | 0.24 | 0.99 |
| **N10_worst** | **81%** | 2.33 | 0.57 |
| **N2_worst** | **90%** | 2.17 | 0.56 |

### 노이즈 × 품질 교차 분석
![noise_quality_cross](images/noise_quality_cross.png)

### 분석 1: 법선이 지배적 요인

단일 요인 최대 수준에서의 val3dity 하락:

| 요인 (최대) | val3dity 하락 |
|------------|:---:|
| **Normal (20°)** | **-53%p** |
| Classification (30%) | -10%p |
| Outlier (10%) | -5%p |
| Missing (50%) | -5%p |
| Area (100%) | -3%p |
| Position (1.0m) | -2%p |

법선(-53%p)이 그 다음(분류, -10%p)보다 **5배 큰 영향**.

![sensitivity_ranking](images/sensitivity_ranking.png)

복합 조건에서 충분조건 검증:

| 조건 | val3dity | 법선 단독 대비 추가 하락 |
|------|:---:|:---:|
| normal_10° 단독 | 84% | — |
| **N10_worst** (N10° + 나머지 전부 최악) | **81%** | **−3%p** |
| normal_2° 단독 | 91% | — |
| **N2_worst** (N2° + 나머지 전부 최악) | **90%** | **−1%p** |

나머지 요인(위치 1m + 분류 30% + 누락 50% + 아웃라이어 10% + 면적 100%)을 **전부 최악**으로 설정해도 val3dity 추가 하락은 −1~3%p에 불과. 법선 10°가 단독으로 −16%p를 설명하므로, 전체 하락(−19%p)의 **84%가 법선에 기인**.

**충분조건 판정**: 법선이 지배적 요인이나, **엄밀한 충분조건은 아님**. N10_worst(81%) < normal_10° 단독(84%)이므로 나머지 요인도 소폭 영향. 다만 실질적으로 **법선만 관리하면 나머지는 무시 가능한 수준**.

![combined_vs_single](images/combined_vs_single.png)

### 분석 2: Roof type별 허용 범위

| | flat | shed | gable | tri-slope | hip | complex |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| clean | 100% | 100% | 100% | 100% | 100% | 100% |
| N2° | 100% | 80% | 99% | 89% | 87% | 79% |
| **N10°** | **98%** | **90%** | **84%** | **85%** | **80%** | **74%** |
| N20° | 71% | 70% | 39% | 44% | 35% | 44% |

- **Flat**: N10°에서 98% — 법선에 가장 강건 (단순 extrusion, ridge 계산 불필요)
- **Gable/hip/complex**: N10°에서 74-84% — 법선에 민감 (ridge/skeleton 계산 필요)
- **Flat 98% vs Complex 74% = 24%p 차이** — 기존 연구(RMSE 2배 차이)와 일관

![roof_type_comparison](images/roof_type_comparison.png)

![roof_type_heatmap](images/roof_type_heatmap.png)

### 분석 3: 구조적 품질과 의미론적 정확성의 차별적 민감도

| 노이즈 | val3dity 변화 | Sem. Acc 변화 | 주된 영향 측면 |
|--------|:---:|:---:|------|
| Normal 20° | **-53%p** | -19%p | **주로 구조적** (val3dity 하락이 2.8배) |
| Classification 30% | -10%p | **-35%p** | **주로 의미론적** (Sem.Acc 하락이 3.5배) |
| Position 1.0m | -2%p | -4%p | 거의 무관 |

두 품질 측면이 완전히 독립적이지는 않으나 (Normal 20°도 Sem.Acc를 −19%p 하락시킴), **지배적으로 반응하는 요인이 다르다**: 법선은 구조적 품질을, 분류는 의미론적 정확성을 주로 결정.

**시사점**: L_sem(분류 감독)은 의미론적 정확성을 개선하지만, 구조적 품질에는 거의 기여하지 못한다. 법선을 개선하는 별도 메커니즘(L_mutual)이 필요. → **설계 선택 2(L_mutual)의 필요성을 뒷받침.**

![structure_vs_semantic](images/structure_vs_semantic.png)

X축=val3dity(구조), Y축=Sem.Acc(의미론). Normal(빨강)은 **좌하향**(val3dity 급락 + Sem.Acc 소폭 하락), Classification(주황)은 **수직 하락**(Sem.Acc만 급락, val3dity 유지). 나머지 요인(회색)은 우상단에 밀집하여 영향 미미. 복합(진한 점)은 양쪽 모두 하락.

### 분석 4: 면적 오차는 영향 없음

| 조건 | val3dity | Chamfer | Sem |
|------|:---:|:---:|:---:|
| area_30% | 99% | 0.12m | 1.00 |
| area_50% | 98% | 0.16m | 0.99 |
| area_100% | 97% | 0.24m | 0.99 |

면적 노이즈: 각 프리미티브의 area에 log-normal 스케일 (예: σ=100%이면 개별 프리미티브 면적이 약 0.5~2배로 변동). 모든 프리미티브에 독립적으로 적용.

면적은 클러스터링에서 plane equation의 가중 평균 가중치로 사용된다. 영향이 없는 이유:
- **법선 방향은 가중치에 둔감**: 같은 면의 30개 프리미티브 법선이 모두 같은 방향이면, 가중치가 달라도 평균 방향은 동일
- **개별 오차가 평균에서 상쇄**: 어떤 프리미티브는 과대, 어떤 건 과소 → 평균에서 상쇄 (√N 효과)

## Stage 2 반영

### 최적화 목표 (Roof type별)

| Roof type | 법선 σ 목표 | 근거 |
|-----------|----------|------|
| flat | ≤20° (여유) | N20°에서도 71% |
| gable/hip/complex | **≤10°** | N10°에서 74-84%, N20°에서 35-44% |

→ L_mutual의 L_vert(벽 법선 수평)와 L_slope(경사 roof 법선)이 핵심.

### 다음 단계
1. **Synthetic B**: L_mutual이 법선 σ≤10°를 달성하는가?
2. **Real**: ISPRS + 성수동에서 전체 파이프라인 + City3D 비교

## 알려진 한계

1. **Clean 완전성 ~93%**: 극단 좁은 건물, 복잡 dormer에서 Stage 3 실패.
2. **Shed 샘플 수 부족**: 10개만 — 통계적 신뢰도 낮음.
3. **Roof type 분류 정밀도**: RoofSurface 면 수 기반 → cross-gable vs simple gable 등 구분 불가.
4. **3D BAG 지역 편향**: 네덜란드 건물만 — 아시아/미국 건물 유형 미포함.

## 시각적 산출물

- `images/noise_quality_cross.png`: 17조건 × 3지표 교차 분석
- `images/sensitivity_ranking.png`: 민감도 순위
- `images/combined_vs_single.png`: 복합 vs 단일
- `images/roof_type_comparison.png`: 6 roof type × 법선 노이즈
- `images/roof_type_heatmap.png`: roof type × 전체 노이즈 히트맵
- `images/structure_vs_semantic.png`: 구조적 vs 의미론적 독립성
- `images/gt_vs_result_comparison.png`: Stage 3 결과 노이즈 변화 비교 (4 roof type × 3조건)
- `viz_samples/*_clean_50.city.json`: CityJSON Ninja 확인용 (3 scene × 50건물)

### Stage 3 Result: 노이즈 증가에 따른 형상 변화
![gt_vs_result](images/gt_vs_result_comparison.png)

**구성**: 행 = 노이즈 조건 (Clean / N10° / N20°), 열 = Roof type (Flat / Gable / Hip / Complex). 각 열은 **동일 건물**을 동일 시점에서 렌더링. Clean 행이 레퍼런스(기준), 이후 행에서 법선 노이즈 증가에 따른 형상 변화를 관찰. 하단에 val3dity(✓/✗), Chamfer distance(CD), Semantic accuracy(SA) 표시.

> **Note**: Chamfer distance는 clean Stage 3 결과(레퍼런스)와의 거리. clean에서 CD=0은 자기 자신과의 비교이므로 정의상 0. 건물은 roof type의 시각적 특징이 Stage 3 결과에서 드러나는 것으로 선택 (경사 지붕면이 실제로 보이는 건물 우선).

**관찰 포인트:**

| Roof type | Clean (reference) | Normal 10° | Normal 20° |
|-----------|-------------------|-----------|-----------|
| **Flat (B485)** | ✓ CD=0 SA=1.00 | 미미한 변형 (CD=0.26m). **전체 형상 유지** | val3dity 실패하나 형상 인식 가능 (CD=0.50m). 단순 extrusion이므로 ridge 계산 불필요 |
| **Gable (B119)** | ✓ CD=0 SA=1.00. 대칭 V자 박공 (slope≈0.70) | Ridge 약간 기울어짐 (CD=0.48m) | **Ridge 붕괴** — 지붕면이 뒤틀림 (CD=0.84m) |
| **Hip (B468)** | ✓ CD=0 SA=1.00. 3개 경사면, 높이 14.9m | 경사면 기울기 변형 (CD=0.64m) | **Ridge 왜곡** + 면 라벨 오류 (CD=1.67m, SA=0.88) |
| **Complex (B175)** | ✓ CD=0 SA=1.00. 5개 지붕(4 경사)+4 wall | **다중 교차점 이동** (CD=1.26m) | 구조 완전 붕괴 (**CD=3.56m**, **SA=0.33**) |

**복잡도에 따른 Chamfer distance 증가 (N10° 기준):**
```
Flat: 0.26m → Gable: 0.48m → Hip: 0.64m → Complex: 1.26m (5× 차이)
```

**핵심 인사이트**: 법선 노이즈의 영향은 **ridge/skeleton 계산의 복잡도**에 비례한다:
- **Flat** (ridge 없음): extrusion만으로 형상 생성 → 법선 변화에 가장 강건
- **Gable** (1 ridge): 두 지붕면의 교차선 1개 계산 → 중간 민감도
- **Hip** (skeleton): straight skeleton으로 여러 ridge 계산 → 민감
- **Complex** (다중 교차): 5개+ 면의 교차점 동시 계산 → 가장 민감 (N10° CD=1.26m, N20° CD=3.56m)

이 시각적 관찰은 정량 결과(Flat 98% → Complex 74% at N10°, 표 참조)와 일치하며, Building3D(ICCV 2023)의 발견(단순 건물 IoU=0.97 → 복잡 건물 IoU=0.36)과도 동일한 경향이다.

**생성 스크립트**: `scripts/stage3_synthetic/plot_gt_vs_result.py`

## 생성/수정 파일

| 파일 | 유형 | 핵심 |
|------|------|------|
| `scripts/stage3_synthetic/buildings_3dbag.py` | 수정 | `classify_roof_type_from_faces()` 추가 |
| `scripts/stage3_synthetic/run_3dbag_experiment.py` | 수정 | 6 roof type 층화 추출 |
| `scripts/building_to_citygml_v4.py` | 수정 | GroundSurface 누락 버그 수정 |
| `scripts/build_2_5d.py` | 수정 | convex hull fallback, make_valid, wall XZ 투영 |
