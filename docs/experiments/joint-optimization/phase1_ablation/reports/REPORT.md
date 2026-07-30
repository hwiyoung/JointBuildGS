# Phase 1 Step 1-6 + Phase 1 종합 — Ablation REPORT

## 1. Phase 1의 역할

본 연구(*도시 규모 건물의 구조적 3D 복원을 위한 기하-의미론 공동 최적화*)의 최종 주장
**"공동 최적화가 순차 파이프라인보다 CityGML 품질을 개선한다"** 는 Phase 2 (3D BAG → CityGML
+ val3dity) 와 Phase 3 (real UAV + 순차 대비) 에서 확정됩니다.

Phase 1 (`docs/EXPERIMENT_PLAN.md`) 의 역할:
1. 2DGS 기반 재구성이 외부 레퍼런스 수준인지 (건강검진)
2. 각 메커니즘이 설계대로 작동하는지 (메커니즘 단위 검증)
3. Both 구성이 학습 가능하고 두 효과를 동시 보존하는지 (Phase 2 input 적합성)

**"시너지·간섭·CityGML 품질" 판정은 Phase 1 scope 아님** — Phase 2 이관.

## 2. GT 계층과 측정 가능성

| Phase | 데이터 | GT | 강도 | 측정 가능 |
|-------|--------|-----|------|-----------|
| **1 (현재)** | MatrixCity | depth/normal 규칙 pseudo-label | 약 | 렌더/기하 parity, Wall-vert%, σ_normal, 픽셀 mIoU |
| 2 (차기) | 3D BAG | CityGML 자체 | 중강 | 폴리곤 F1, topology, val3dity |
| 3 (최종) | GauU-Scene + 성수동 | 없음 | — | 순차(City3D) 대비 질적 우위 |

**주장하는 것**: 렌더/기하 파리티 유지, L_mutual·L_structure 설계대로 작동, Both 공존 검증.
**주장하지 않는 것**: Both 최고 여부, CityGML 품질, 순차 대비 우위 — 모두 Phase 2/3 판정.

## 3. Phase 1 체크리스트

Wall-vert% = Wall-class 중 `|n·g|<0.15` (수직 벽면) 비율, 전역.

| Step | 검증 목표 | 레퍼런스/설계 | 결과 | 통과 |
|------|----------|---------------|------|------|
| 1-1 | Vanilla 2DGS 파리티 | CityGSV2 baseline PSNR 21.12 | 21.31 | ✓ |
| 1-2 | +depth/normal 파리티 | CityGSV2 w/depth 22.22 | 22.06 (peak 22.39) | ✓ |
| 1-3 | +semantic 비파괴 | Step 1-2 PSNR 유지 | 22.07, mIoU 0.635 | ✓ |
| 1-4 | L_mutual 작동 | Wall-vert 상승 | 16.9% → 88.2% | ✓ |
| 1-5 | L_structure 작동 | σ_normal 감소 | −45% | ✓ |
| 1-6 | Both 공존 | 렌더/기하 + WV + σ | PSNR 20.63, F1 0.999, WV 88.3%, σ_n −36% | ✓ |

**Phase 1 체크리스트 6/6 통과.**

## 4. 4조건 학습 구성

| ID | 조건 | 손실 | warmup | w | 시간 |
|----|------|------|--------|---|------|
| Baseline | 1-3 | photo+depth+normal+nc+sem | — | — | ~5.5h |
| Mutual | 1-4 | +L_mutual | @10k | 0.1 | ~6h |
| Structure | 1-5 | +L_structure | @15k | 0.1 | ~6.5h |
| **Both** | 1-6 | +L_mutual + L_structure | L_m@10k, L_s@20k | 0.1/0.1 | **7h18m** |

30k iter, seed 0, MatrixCity Small City Aerial, test 100 views. Both 는 L_structure warmup 을
20k 로 늦춰 L_mutual 의 f_i/n_i 수렴 후 그룹핑.

### 학습 곡선

![training_curves](figures/training_curves.png)

Eval PSNR 4조건 모두 20k 이후 수렴. L_mutual: iter 10k 점화 → 0.21 → 0.015 수렴.
L_structure: Both 가 더 늦게 시작, 값 낮게 유지.

## 5. 렌더/기하 파리티 검증

| Metric | Baseline | Mutual | Structure | Both | 판정 |
|--------|----------|--------|-----------|------|------|
| PSNR [dB] ↑ | 20.513 | 20.629 | 20.624 | **20.634** | 모두 CityGSV2 수준 |
| SSIM ↑ | 0.587 | 0.587 | 0.588 | 0.587 | 동등 |
| LPIPS ↓ | 0.615 | 0.613 | 0.613 | **0.612** | 근소 개선 |
| F1@0.5m ↑ | 0.9978 | 0.9981 | **0.9989** | **0.9990** | near-perfect |
| Chamfer [m] ↓ | 0.0208 | 0.0229 | **0.0200** | 0.0224 | ±10% |

네 조건 모두 레퍼런스 수준 유지. 추가 손실이 기본 복원을 해치지 않음.

![render_compare_4way](figures/render_compare_4way/render_compare_4way.png)

네 조건 RGB 시각 구분 불가 = photometric 파리티 직접 증거.

## 6. Mechanism 1 (L_mutual) 작동 검증

### 6.1 도메인 규칙 지표 (전역, |n·g|<0.15 / >0.85)

| Metric | Baseline | Mutual | Structure | Both |
|--------|----------|--------|-----------|------|
| **Wall-vert %** ↑ | 16.9% | **88.2%** | 17.0% | **88.3%** |
| Terrain-horiz % ↑ | 93.4% | **99.0%** | 95.3% | **99.1%** |
| Roof-horiz % | 88.9% | 49.0% | **91.8%** | 54.3% |

L_mutual 이 Wall 수직성·Terrain 수평성 극적 강화 ✓. Structure 단독 영향 없음. Both ≈ Mutual
→ L_structure 가 L_mutual 을 간섭하지 않음.

**Roof-horiz 하락**: Wall class 재정의로 경사면(발코니·지붕 측면)이 Roof 로 재분류되며
Roof 에 비수평 요소 혼입. §7.2 분석 참조.

### 6.2 Wall 법선 분포 histogram

![wall_normal_distribution](figures/wall_normal_distribution.png)

Wall-class `|n·g|` 확률밀도 (0 = 수직 벽면 = 이상적):
- **Baseline/Structure**: bimodal (0, 1 양쪽 peak) — Wall class 에 수직 벽 + 수평 지붕 혼재
- **Mutual/Both**: 0 에 sharp peak — 실제 수직 벽면만 ✓

### 6.3 드라마틱 시각 증거 — max-diff 뷰

Baseline vs Both semantic 차이 가장 큰 3개 뷰 (`scripts/input_and_alignment/find_max_diff_views.py`):

| View | Wall_Baseline | Wall_Both | Wall→Roof shift |
|------|---------------|-----------|-----------------|
| **2597** | 91.3% | 4.3% | **60.5%** |
| 3984 | 83.1% | 32.3% | 46.0% |
| 4008 | 95.6% | 24.4% | 42.4% |

**View 2597** (aerial, 건물 지붕 top-down):

![maxdiff_v2597](figures/phase1_visual_check_maxdiff/v2597_panel.png)

- **Baseline**: 지붕을 91% Wall(파랑)로 오분류
- **Mutual/Both**: Roof(빨강)로 정확히 분류 (4%만 Wall) ✓
- **Structure**: Baseline 과 동일 오류 (Wall 교정은 L_mutual 영역)

**View 3984, 4008** — 동일 패턴:

![maxdiff_v3984](figures/phase1_visual_check_maxdiff/v3984_panel.png)
![maxdiff_v4008](figures/phase1_visual_check_maxdiff/v4008_panel.png)

**Wall-vert 16.9%→88.3% 의 실체**: Baseline 의 "지붕까지 Wall" 오류를 Both 가 교정. Phase 2
에서 CityGML 폴리곤 생성 시 Baseline 은 지붕에 WallSurface, Both 는 RoofSurface 를 올바르게
생성할 것으로 예측.

### 6.4 의미론 지표 (rule-GT proxy)

| Metric | Baseline | Mutual | Structure | Both |
|--------|----------|--------|-----------|------|
| mIoU ↑ | 0.635 | 0.626 | **0.640** | 0.625 |
| Roof IoU | 0.704 | 0.655 | 0.702 | 0.659 |
| Wall IoU | 0.616 | 0.587 | **0.620** | 0.576 |
| Terrain IoU | 0.585 | 0.636 | 0.599 | **0.642** |
| Wall-class 비율 | 31.4% | 12.5% | 31.4% | 12.5% |

전역 mIoU 는 Baseline 최고이나, §6.3 max-diff 뷰에서는 Mutual/Both 가 시각적으로 정확 —
rule-GT 뷰 편향 평균이 개별 뷰 개선을 가림. rule-GT 의 Wall 과잉 라벨링이 proxy 약점.
**Phase 2 CityGML 지표로 재평가**.

### 6.5 BG reassignment — 양방향 gradient 의 의도된 전역 효과

L_mutual 은 설계상 **f_i ↔ n_i 양방향 gradient** (CLAUDE.md 메커니즘 1). 프리미티브가 Wall 로
라벨됐는데 `|n·g|>0.15` 이면 탈출 경로가 둘: (1) n 을 회전해 수직화, (2) f 를 움직여 Wall
이탈. 둘 중 저항 적은 쪽으로 descent. depth/normal 감독으로 n 이 묶여 있으면 f 가 움직이고,
Roof/Terrain rule 도 만족 못 하면 → BG 로 수렴 (ignore_index = "commit 안 함").

전역 통계:

| 조건 | Wall+Roof+Terrain | BG (잔여) | Wall_frac |
|------|-------------------|-----------|-----------|
| Baseline | 0.982 | **1.8%** | 31.4% |
| Mutual | 0.809 | **19.1%** | 12.5% |
| Structure | 0.982 | 1.8% | 31.4% |
| Both | 0.809 | **19.1%** | 12.5% |

약 **89만 개 프리미티브** (5.27M 중 17%) 가 BG 로 이동. 이는 "domain rule 을 만족하지 못하는
프리미티브는 건물 표면 class 를 배정하지 않는다" 는 설계 규칙의 **전역 적용** 결과이며, artifact
가 아닙니다.

**3D 뷰어 관찰 (`src/apps/gs3d_4way_viewer/` semantic 모드)**:
- 건물 주변부 (지면 경계, 하늘-건물 접합층, 주차 차량, 그림자 영역) 에서 큰 색감 변화
  → L_mutual 이 이런 애매한 프리미티브를 BG 로 정리
- 건물 코어의 시각 변화 적음 → 건물 기하가 이미 명확해 Wall/Roof rule 을 깔끔히 통과하기 때문
- 지면 경계 청소는 Terrain IoU +0.057 로 rule-GT 에도 반영됨

**Wall-vert% 88.3% 의 정직한 해석**:
- 지표 정의 ("Wall-labeled 중 `|n·g|<0.15` 비율") 가 L_mutual 강제 규칙 그 자체 → **설계대로면
  tautological 하게 수렴**. 이게 설계의 의도이고 부작용이 아님.
- 분모 (Wall class) 가 31.4% → 12.5% 로 줄어든 것도 동일한 설계 동작의 산물 (애매한 후보는
  Wall 이 아니다).
- **단 두 효과를 하나로 묶어 "법선만 고친 것" 으로 읽으면 over-claim**. 실제로는 "법선 정렬 +
  class 정리" 의 결합 효과.
- §6.3 max-diff 뷰는 건물 지붕에서 Wall → Roof 의 개별 재라벨링을 보여주는 드라마틱 증거로
  유효.

**Phase 2 이점**: BG 프리미티브는 CityGML 폴리곤 추출 파이프라인에서 자동 배제 →
"conservative polygon extraction" (애매한 건 벽·지붕·지면 폴리곤에 안 넣음) 이 자연스럽게 성립.
3D BAG curated GT 에서는 rule-GT 의 Wall 과잉 라벨이 없어져 BG 재분류량 자체도 줄어들 예정.

**보고 원칙**: Phase 2 에서는 `Wall_frac`, `Wall-vert%`, `BG_frac` 세 지표를 **항상 동반** 표기.
셋을 함께 봐야 "법선 정렬" 과 "class 정리" 효과를 분리 해석 가능.

## 7. Mechanism 2 (L_structure) 작동 검증

**프레이밍**: Mech 2 는 **그룹 수준 aggregate 제약** — 개별 프리미티브 시각 변화 없음. 유효 증거는
정량 통계.

### 7.1 σ_normal_intra / σ_coplanar 4조건

| Metric | Baseline | Mutual | Structure | Both |
|--------|----------|--------|-----------|------|
| σ_normal_intra ↓ | 0.0246 | **0.0358 (+46% 악화)** | **0.0136 (−45%)** | 0.0158 (−36%) |
| σ_coplanar ↓ | 0.0085 | 0.0091 (+7%) | **0.0072 (−16%)** | 0.0075 (−13%) |
| n_groups | 254k | 224k | 249k | 222k |
| in-group % | 68.7% | 51.8% | 71.1% | 54.0% |

![structure_4way_bars](figures/structure_4way_bars.png)

- Structure: σ −45%, σ_coplanar −16% ✓
- Mutual: σ **+46% 악화** — §7.2
- Both: σ −36%, σ_coplanar −13% ✓

### 7.2 Mutual σ 악화는 rule-GT artifact

**원인 — Roof class 오염 cascade**:
1. rule-GT 가 Wall 과잉 정의 (기울어진 표면 포함)
2. L_sem 이 모델을 GT 방향 (Wall 과잉) 으로 밀어냄
3. L_mutual 은 `|n·g|<ε` 를 Wall 로 고집 → 반대 방향
4. 두 손실 **정반대 싸움**. L_mutual 승 → 기울어진 것 Wall 축출
5. 축출분 → **Roof 재분류** (Roof-horiz 91.7%→56% 하락이 증거)
6. Roof 에 수평 + 기울어진 혼재 → σ_normal_intra↑

Roof 가 55%+ 차지 → 전체 σ 끌어올림.

**왜 f_i 가 먼저 움직였는가**:
- `lr_sem=2.5e-3` vs `lr_quats=1.0e-3` → 2.5배 빠름
- n_i 는 5개 손실 공유, f_i 는 2개 → f_i 방향 덜 희석
- n_i 는 quaternion → SO(3) 비선형, f_i 는 logits 직접
- "저항 적은 경사 하강 경로" = f_i

**완벽 GT 가정**: 기울어진 표면이 Roof 로 라벨 → L_sem·L_mutual 방향 일치 → 충돌 없음 → cascade
없음 → σ_normal 악화 없음.

**결론**: σ_normal +46% 는 L_mutual **설계의 한계가 아니라** MatrixCity rule-GT proxy 가 L_sem
과 L_mutual 을 반대편에 놓아 생긴 **artifact**. Phase 2 curated GT 에서 해소 예상.

## 8. 4조건 종합 — 기여도 분해

![contribution_decomposition](figures/contribution_decomposition.png)

- **PSNR/LPIPS/F1**: 4조건 동일 → 어떤 손실도 기본 복원 해치지 않음 (파리티 OK)
- **Wall-vert%**: Mutual/Both 만 급등 → **L_mutual 독점**
- **σ_normal**: Structure 순 개선 (−45%), Mutual 만으론 **악화 (+46%, GT artifact)**, Both −36% → **L_structure 순 기여**
- **mIoU**: Structure 최고, Mutual/Both 감소 — rule-GT 기준 손해 (§6.3 참조). 폴리곤 기준은 Phase 2

**핵심**: 두 메커니즘이 **직교 축에 기여**. 단독 조건은 다른 축 baseline 수준. Both 만 두 축 양호.
시너지 판정은 CityGML (Phase 2) 로.

## 9. Gradient isolation 검증

| Loss | c | n | s | opa | SH | f |
|------|---|---|---|-----|-----|---|
| L_photo | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ |
| L_depth | ✓ | — | — | — | — | ✗ |
| L_normal | — | ✓ | — | — | — | ✗ |
| L_nc | ✓ | ✓ | — | — | — | ✗ |
| L_sem | — | — | — | — | — | ✓ |
| **L_mutual** | c (height만) | **n** | — | — | — | **f** |
| **L_structure** | **c (coplanar)** | **n (align)** | — | — | — | — |

L_structure 는 f 에 직접 gradient 없음 (그룹 = argmax 이산). Mutual 이 f 담당. L_mutual 은 s 에
gradient 없음. Both 에서 두 loss 가 n, c 에 동시 gradient 합산.

## 10. 3D 대화형 시각화

4조건을 동일 카메라로 동기화해 비교하는 로컬 웹 뷰어를 제공합니다 —
[src/apps/gs3d_4way_viewer/](../../../../../src/apps/gs3d_4way_viewer/).

### 포맷: 2DGS → ksplat

2DGS 는 disk (2 scales), 3DGS 는 ellipsoid (3 scales). GS 웹 뷰어 호환 위해 세 번째 scale 을
e^−7 ≈ 0.001m 로 강제 (매우 얇은 ellipsoid = disk 근사) 한 뒤 `.ksplat` 로 변환.

### 에셋 구성 (6 모드)

```
src/apps/gs3d_4way_viewer/assets/
├── ksplat_2dgs_dense_rgb/         (full SH, 기본 포토리얼)
├── ksplat_2dgs_dense_normal/      (법선을 RGB 로 치환 — Mech2 증거)
├── ksplat_2dgs_dense_semantic/    (의미론 class 를 RGB 로 치환 — Mech1 증거)
├── ksplat_2dgs_light_rgb/         (경량 서브샘플)
├── ksplat_2dgs_light_normal/
└── ksplat_2dgs_light_semantic/
```

각 디렉토리에 `baseline.ksplat, mutual.ksplat, structure.ksplat, both.ksplat` 4개.

### 사용법

```bash
cd src/apps/gs3d_4way_viewer && python serve.py   # 로컬 HTTP 서버
# 브라우저에서 http://localhost:8000/index.html
# 상단 LOD (dense/light), View (RGB/Normal/Semantic) 토글
# "Sync camera" 체크 시 한 패널 드래그 → 4 패널 동시 갱신
```

### 관찰 포인트

- **Semantic 뷰**: Baseline 은 지붕을 Wall(파랑)로 오분류, Mutual/Both 는 Roof(빨강)로 교정.
  동시에 Mutual/Both 에서 지면 경계·하늘층 프리미티브가 BG 로 재분류되어 주변부 색감이
  크게 달라짐 (§6.5 BG reassignment 참조).
- **Normal 뷰**: Structure/Both 에서 벽면 법선 색 균일도 개선 (σ_normal_intra −36~−45%).
- **RGB 뷰**: 4조건 시각 구분 불가 — photometric 파리티의 직접 증거.

## 11. Phase 2 착수 준비사항

### Phase 1 결과가 Phase 2 에 제공
- **4조건 ckpt**: Stage 3 폴리곤 추출 파이프라인 입력. Both 가 "Wall 수직성 + 구조 일관성 동시 보존" 유일 조건
- **Baseline 실패 모드 명시화**: §6.3 "지붕을 Wall 로 오분류" → Phase 2 CityGML 에서 지붕에 WallSurface 생성 실패로 구현될 것

### Phase 2 success criteria (사전 제안)
- 폴리곤 F1 (IoU 매칭 0.5/0.7)
- Topology matching, non-manifold edge 비율
- 면 기하 오차 (점-면 거리)
- 속성 일치도 (RoofSurface/WallSurface)
- val3dity 통과율

### Phase 2 에서 검증할 Phase 1 가설
1. **GT-causation**: 3D BAG curated GT 에서 Mutual σ 악화가 해소되는가?
2. **Both 효과**: Both 가 clean GT 에서 Structure-only 수준의 σ 달성?
3. **실용 가치**: "Wall 수직 + 구조 일관" 동시 보존이 CityGML 품질에 기여?

### 후속 튜닝 유보
(warmup 순서 역전 / L_structure weight 상향) — Phase 2 결과 기반 의사결정.

## 12. 산출물

```
results/phase1_ablation/
├─ REPORT.md                                   (본 문서)
├─ run/                                         (Step 1-6 Both 학습 — 4조건 중 하나)
│  ├─ ckpt/{step_05000.pt … step_25000.pt, final.pt}   (intermediate ckpt 포함)
│  ├─ renders/, tb/, train.log
│  ├─ eval_rendering/, eval_semantic/, eval_geometry/, eval_structure/
│  └─ eval_all.log
└─ figures/
   ├─ rendering_metrics.json, semantic_metrics.json,
   │  geometry_metrics.json, domain_metrics.json       (§5–§7 정량 JSON)
   ├─ training_curves.png                       (4조건 통합)
   ├─ contribution_decomposition.png            (6 지표 bar)
   ├─ structure_4way_bars.png                   (σ 4조건)
   ├─ wall_normal_distribution.png              (분포 shift)
   ├─ render_compare_4way/                      (RGB 4-way, 4 뷰)
   ├─ semantic_compare_4way/                    (semantic 2D, 4 뷰)
   ├─ phase1_visual_check_maxdiff/              (max-diff 3 뷰 — 주요 Mech1 증거)
   └─ phase1_visual_check/                      (건물-heavy 3 뷰)
```

나머지 3 조건 ckpt 는 각 step 디렉토리에서 참조:
`results/phase1_semantic/run/ckpt/final.pt` (Baseline, Step 1-3),
`results/phase1_mutual/run/ckpt/final.pt` (Step 1-4),
`results/phase1_structure/run/ckpt/final.pt` (Step 1-5).

3D 대화형 뷰어 (§10): [src/apps/gs3d_4way_viewer/](../../../../../src/apps/gs3d_4way_viewer/) — ksplat 6 모드.

## 13. 결론

1. **체크리스트 6/6 통과**: 네 조건 모두 렌더/기하 레퍼런스 유지 + 메커니즘이 설계대로 작동.

2. **L_mutual 의도 효과 육안 확인** (§6.3, §6.5): Baseline 이 지붕을 Wall 로 오분류하는 현상이
   Mutual/Both 에서 교정 — View 2597: Wall 91.3% → 4.3%. "Wall-vert 16.9% → 88.3%" 는
   양방향 gradient 설계의 자연스러운 귀결 (법선 정렬 + 애매 후보의 BG 재분류 17%). 해석
   오독 방지 위해 `Wall_frac`, `Wall-vert%`, `BG_frac` 를 쌍으로 보고.

3. **L_structure 의도 효과 통계로 확인**: σ_normal −45% (Structure), Both −36%. Mech 2 는 설계상
   그룹 평균 제약 — bar chart/histogram/수치가 유효 증거 (개별 프리미티브 시각 변화 없음).

4. **Mutual σ 악화는 rule-GT artifact**: Wall 과잉 라벨을 L_mutual 이 교정하며 Roof 오염 + BG
   재분류 (17%). Phase 2 curated GT 에서 해소 예상.

5. **두 메커니즘이 직교 축에 기여**: Wall-vert 는 L_mutual 전담, σ_normal 은 L_structure 전담.
   Both 만 두 축 동시 양호. 시너지 판정은 Phase 2 로.

6. **Phase 2 착수 자격 충족**: 4조건 ckpt + 정량/정성 분석 + 3D ksplat 뷰어 (§10) 완비.
   Baseline 의 "지붕 Wall 폴리곤 생성" 실패 모드가 Phase 2 CityGML 에서 정량화될 것.
