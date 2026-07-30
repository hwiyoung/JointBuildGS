# Progress Brief — for methodology sketch iteration (Claude Web)

> 본 문서는 **claude web 에 작성된 초기 연구 스케치** 를 수정할 목적으로, Phase 1 ~ Phase 2-2 완료까지의 실험 결과 + 검증된 가설 / 틀린 가설 + 열린 질문을 한 번에 담는다. 방법론은 축약 인용하고, **실험으로 확인된 것 / 확인 후 틀린 것 / 수정이 필요한 것** 을 중심으로 기술한다.
>
> Last updated: 2026-04-25 KST (Phase 2-2 전체 완료 + 진단 실험 D1-D4 반영)

---

## Part I. 연구 프레임 (스케치 원형)

### I.1 문제 정의

건물의 구조적 3D 모델 (소수 평면 + 면 단위 의미론 + watertight solid) 을 **영상** 에서 생성한다. 기존 순차 파이프라인의 3가지 실패 모드:

| 그룹 | 실패 모드 | 기존 한계 | 대응 메커니즘 |
|---|---|---|---|
| A | 구조 추출 부정확 (오병합/누락/교차선) | 일회성 RANSAC | 메커니즘 2 (inter, L_structure) |
| B | 도메인 지식 미반영 | 하드코딩 post-hoc filter | 메커니즘 1 (intra, L_mutual) |
| C | 오류 교정 불가 (일방향 전파) | 상위 stage 가 하위 stage 를 못 고침 | 전체 framework (미분 가능 + 양방향) |

### I.2 핵심 연구 질문

**"왜 RANSAC 대신 미분 가능 최적화로 건물 구조를 추출하는가?"**

### I.3 방법 요약

- **Stage 1**: SfM/MVS + 2D segmentation + gravity 추정 (1회 precompute)
- **Stage 2**: gsplat/2DGS + **L_mutual (intra) + L_structure (inter)** 공동 최적화
- **Stage 3**: 클러스터링 → 평면 교차 → 건물 분리 → GroundSurface → CityGML (val3dity 검증)

**핵심 기여**: 메커니즘 1 의 `p_c × 기하오차` 양방향 gradient + 메커니즘 2 의 주기적 그룹 재할당 → **순환 효과** (서로의 출력을 서로 개선). 순차 파이프라인과 차별화.

### I.4 검증 계획 (원 스케치)

| Phase | 데이터 | 목적 | 주 지표 |
|---|---|---|---|
| 1 | MatrixCity | 레퍼런스 (CityGSV2, ULSR-GS) 대비 달성 | PSNR, mIoU |
| 2 (-1) | 3D BAG 합성 | Stage 3 end-to-end 검증 | val3dity 통과율, 면 IoU, Hausdorff |
| 2 (-2) | Synthetic B | 노이즈/카메라 민감도 | 위 지표 + 조건별 변화 |
| 3 | 성수동 + GauU-Scene | 실데이터, 순차 baseline 비교 | 위 지표 + 순차 파이프라인 대비 |

---

## Part II. 실험 결과로 확인된 것 / 확인 후 틀린 것

### II.1 Phase 1 (MatrixCity) — 완료, 체크리스트 6/6 통과

| Step | 추가 손실 | eval PSNR | 주요 효과 |
|---|---|---|---|
| 1-1 | (vanilla 2DGS) | 21.31 | CityGSV2 baseline 21.12 초과 ✓ |
| 1-2 | +L_depth/normal | 22.06 | CityGSV2 w/depth 22.22 근접 ✓ |
| 1-3 | +L_sem | 22.07 | mIoU 0.635 |
| 1-4 | +L_mutual | 22.24 | **Wall vertical-frac 19% → 91%** |
| 1-5 | +L_structure | 22.16 | **σ_normal_intra −45%**, σ_coplanar −16% |
| 1-6 | Both | 22.26 peak 22.44 | Wall-vert 88.3%, σ_normal −36% |

**해석**: Phase 1 에선 각 메커니즘이 **설계대로 단독 효과 확인**. 시너지 판정은 Phase 2 로 이관.

### II.2 Phase 2-1 (데이터 파이프라인) — 완료

v1/v2 실패 (camera frame bug, biased split, view 부족, 인위적 grid) 를 거쳐 **Pix4D 표준 + 자연 Amsterdam Jordaan 블록** 으로 재설계. 560 views × 131 건물 × procedural texture. FC-1/2/3 통과. 상세는 `results/phase2_synthesis/REPORT.md`.

### II.3 Phase 2-2 (4 조건 ablation) — **완료**

#### Stage 2 결과 (primitive quality)

| 지표 | Baseline | Mutual | Structure | Both | Phase 1 비교 |
|---|---|---|---|---|---|
| eval PSNR (held-out) | 40.35 | 40.93 | 40.96 | 39.81 | 비슷 (40-41) |
| **Wall vertical-frac** | 28.0% | **79.3%** ↑ | 28.4% | **79.4%** ↑ | Phase 1 19→91% 와 일관, magnitude 약간 작음 |
| σ_normal_intra (deg) mean | 14.74 | **12.63** ↓ | 14.88 | 12.99 | **Phase 1 대비 L_structure 효과 거의 없음** (Phase 1 −45% vs Phase 2 +1%) |
| σ_coplanar (m) median | 1.91 | 1.84 | 1.86 | 2.01 | 미세 |
| Roof class fraction | 40.0% | 42.1% | 40.2% | 42.3% | L_mutual 이 Terrain → Roof 재분류 유도 |

#### Stage 3 결과 (CityGML — convex polytope)

| 지표 | Baseline | Mutual | Structure | Both |
|---|---|---|---|---|
| val3dity pass | 40.5% | **32.1%** ↓ | **43.5%** ↑ | **43.5%** ↑ |
| face IoU matched | 0.213 | **0.238** ↑ | 0.220 | 0.230 |
| Hausdorff (m) | 11.42 | 11.33 | 11.39 | 11.46 |
| Semantic accuracy | 21.1% | 20.0% | 21.8% | 19.5% |

#### Roof type 별 val3dity

| Type | Baseline | Mutual | Structure | Both | 경향 |
|---|---|---|---|---|---|
| **complex (L/U, 29동)** | 41.4% | 37.9% | **55.2%** | **55.2%** | Structure/Both +13.8%p ↑ |
| hip (23동) | 34.8% | 34.8% | 47.8% | **52.2%** | Structure/Both ↑ |
| tri-slope (26동) | 26.9% | 30.8% | 34.6% | **38.5%** | Structure/Both ↑ |
| gable (28동) | **53.6%** | 25.0% | 42.9% | 42.9% | **Mutual −28.6%p ↓** |
| flat (25동) | 44.0% | 32.0% | 36.0% | 28.0% | **Mutual/Both ↓** |

#### GT 상한 검증

Stage 2 primitive 가 이상적 (GT 수준) 이라도 Stage 3 알고리즘 자체의 천장 존재:

| 방식 | val3dity |
|---|---|
| GT direct (topology 보존 변환) | **93.9%** (절대 상한) |
| GT + convex polytope | 76.3% (알고리즘 천장, 우리 Stage 3 선택) |
| GT + 2.5D hybrid | 67.2% |
| GT + PolyFit (CGAL + SCIP) | 0% (watertight 변환 미완) |

→ **Convex 방식은 L/U 22% 건물을 구조적으로 처리 불가**. 우리 Best (Both, 43.5%) = convex ceiling 76.3% 의 57%.

### II.4 검증된 가설 / 틀린 가설 / 미확정

#### ✅ 확인된 가설

| 주장 | 증거 |
|---|---|
| **L_mutual 의 Wall 수직화 효과** | Phase 1 19→91%, Phase 2 28→79% |
| **L_mutual 이 Stage 2 primitive 를 직접 수정** | loss/mutual peak 91 → 수렴 0.003, Wall vertical-frac 직접 개선 |
| **복잡 건물 (L/U, hip) 에서 L_structure/Both 효과** | val3dity +13.8%p (complex), +17.4%p (hip with Both) |
| **Phase 1 결과 Phase 2 일부 전이** | Wall vertical-frac 은 전이됨 |

#### ❌ 실측 후 틀린 가설

| 내가 주장했던 것 | 실제 검증 결과 |
|---|---|
| "photo consistency loss 가 L_mutual 에 저항한다" | TB r(mutual, photo) = **−0.03 (무상관)**. peak 시점 photo 오히려 낮음 |
| "L_structure 효과 없는 원인은 데이터 복잡도" | Phase 1/2 의 loss magnitude 비슷 (0.0003 vs 0.0003). 다른 원인 |
| "w_structure 올리면 해결" | Phase 2 의 structure/photo ratio 가 Phase 1 보다 **20x 오히려 큼**. w 문제 아님 |
| "기울어진 벽 (처마/장식) 때문에 L_mutual 회귀" | **GT wall 2334 개 전체가 완벽 수직 (< 0.1° 편차)**. 기울어진 벽 자체가 존재 안 함 |
| "mutual_height 분리하면 tug-of-war 완화" | tug-of-war 자체가 없음. mutual_height peak 91 은 초반 dynamics 일 뿐 |

#### ⚠ 미확정 원인 → 진단 실험 D1-D4 결과

**D1 (bid=2 case study)**: bid=2 (flat, 4 walls 박스) 에서 Baseline → Mutual 갈 때 Stage 3 Step 2 (clustering) 가 wall 그룹 4 → 2 로 줄어들고 polytope 의 face 가 부족해져 203 (non-planar) 발생. **하지만 다른 건물 (bid=22 gable, bid=21 complex)** 에선 다른 패턴 — D1 의 cluster 병합 메커니즘은 **사례 단위 설명**, 일반화 불가.

**D2 (L_structure grouping output)**: 3 건물 비교 결과:
- bid=2 (flat): σ_normal_intra Baseline 19.46° → Structure 17.00° (**−13%**) ✓
- bid=6 (hip): 16.22° → 16.04° (**−1%**, 측정 노이즈 수준)
- bid=21 (complex): 16.52° → 16.92° (**+2%**, 약간 악화)
- 전체 131 건물 평균: **+1%** (효과 부재)
- → L_structure 가 **단순 건물에서 약하게 작동, 복잡 건물에선 약간 악화**. 평균 0 은 "효과 없음" 이 아니라 "이질적 효과 상쇄"

**D3 (Stage 3 6-step breakdown, 4 buildings)**:
- bid=2 (flat): Mutual fail / 나머지 pass
- bid=22 (gable): Baseline fail / 메커니즘 모두 pass
- bid=6 (hip): Baseline + Both fail / Mutual + Structure pass
- bid=21 (complex): Structure + Both fail / Baseline + Mutual pass
- → **건물별 매우 이질적**. 단일 메커니즘이 보편적 우열 없음. 집계 수준에서만 통계적 우세 (Structure/Both > Baseline > Mutual).

**D4 (Baseline Wall 비수직 공간 패턴)**:
- Baseline Wall 의 **4-5% 만 < 1° 완전 수직**, 평균 tilt 12-15°
- **코너 영역 (d<1m)**: tilt 16.5°, %<5° = 20% (가장 나쁨)
- **벽면 가운데 (d<10m)**: tilt 12.2°, %<5° = 25%
- **Mutual + Both 에선 코너 영역 tilt 2.76°, %<5° = 81%** (uniformly fixed)
- → **L_mutual 의 per-primitive intra 메커니즘이 spatial dependency 추가 없이 corner 문제 자연스럽게 해결**

**D1-D4 종합 결론**:
- L_mutual 의 Stage 2 효과 (Wall 수직화) 는 의도대로 작동, 공간적으로 균질
- L_structure 의 Stage 2 효과 (σ_normal_intra) 는 매우 약함, 건물별 이질적
- Mutual 의 Stage 3 회귀는 단일 메커니즘으로 설명 안 됨 (cluster 병합은 일부 사례)
- "순환 효과" 시너지 미입증. Both 는 Mutual 의 회귀를 Structure 가 부분 상쇄하는 정도

### II.5 연구 주장별 증거 현황 (업데이트)

| 주장 | Phase 1 | Phase 2-2 | 판정 |
|---|---|---|---|
| Aerial GS benchmark 레퍼런스 수준 | ✓ PSNR 22.26 | — | **달성** |
| 메커니즘 1 (L_mutual) 단독 효과 = 벽 수직화 | ✓ 19→91% | ✓ 28→79% | **달성** |
| 메커니즘 2 (L_structure) 단독 효과 = 면 정렬 | ✓ σ_normal −45% | **✗ σ_normal +1% (효과 부재)** | **미달성 (원인 미확정)** |
| Both 의 시너지 (단순 합 이상) | — | **✗ 관찰 안 됨** (Mutual 지배, Structure 의 Mutual 회귀 상쇄) | **미달성** |
| CityGML val3dity 통과 | — | ✓ +3%p (Structure/Both) | 부분 달성 (절대 수치 40-44%, ceiling 76.3%) |
| 순차 파이프라인 대비 우위 | — | 미측정 | Phase 3 or 별도 측정 |

---

## Part III. 스케치 수정이 필요한 부분 (이번 업데이트에서 새로 보강)

### III.1 평가 지표 프레임 재정립 (Phase 2-2 에서 심화 확인)

기존 발견 + 이번 업데이트:
- **합성 데이터에서 eval 지표 saturation** (PSNR 40, normal cos 0.98) — 기존 관찰
- **Stage 3 (val3dity, face IoU) 도 메커니즘 차이를 모두 포착 못함** — 이번 업데이트:
  - Mutual 이 face IoU 최고 (0.238) 하지만 val3dity 회귀 (32.1%)
  - Structure 가 val3dity 최고 하지만 face IoU 평범 (0.220)
  - 각 지표가 서로 다른 축 측정 → 단일 지표로 "우월" 판단 불가

**제안**: 스케치의 "지표의 역할 분리" 를 **세 축** 으로 확장
- 축 1: 렌더링 품질 (PSNR, SSIM)
- 축 2: Primitive 기하 (σ_normal_intra, σ_coplanar, Wall vertical-frac)
- 축 3: CityGML 구조 (val3dity, face IoU, Hausdorff, SemAcc)

각 메커니즘이 **어느 축에 기여** 하는지 명시.

### III.2 Stage 3 알고리즘 선택의 명시화 (NEW)

기존 스케치는 "Stage 3 = 클러스터링 → 평면 교차 → 빌딩 분리 → CityGML" 로만 서술. 구체 알고리즘 선택이 **본질적으로 상한을 결정** 한다는 점을 반영해야:

| Stage 3 옵션 | GT ceiling | footprint 입력? | 구현 상태 |
|---|---|---|---|
| Convex polytope (현재) | 76.3% | ✗ | 완성 |
| 2.5D hybrid (Synthetic A 용) | 67.2% | ✗ (내부 추출) | 버그 있음 |
| PolyFit (Nan 2017) | ? (예상 85%+) | ✗ | **미완** (watertight post-proc) |
| City3D / Roofer | 예상 90%+ | ✓ | 미도입 |

**스케치 수정**: "Stage 3 알고리즘 선택이 연구 상한을 결정한다. 현재 convex 는 L/U 건물 22% 를 구조적으로 처리 불가. PolyFit 완성 or City3D 전환 시 상한 상승 가능."

### III.3 연구 포지셔닝 재검토 (NEW)

Phase 2-2 결과로 **포지셔닝의 불명확성** 발견:
- Image-only 파이프라인 (우리) val3dity **40-44%**
- LiDAR + footprint 기반 (City3D, Roofer): **85-90%+**
- **입력 가정이 다른데 같은 지표로 비교** → "왜 우리 방법을 쓰나" 에 답하기 어려움

**해결책 3 가지 (스케치에 반영 필요)**:

- **틀 A**: CityGML val3dity 중심 → 절대 수치 40% 설득력 부족, LiDAR 기반과 직접 비교 부적절
- **틀 B**: 구조적 3D 복원 다면 평가 — CityGML 은 하나의 downstream 증거, multi-metric (Wall vertical, σ_normal, face IoU, val3dity, Chamfer 등) 으로 메커니즘 기여 종합 → **권장**
- **틀 C**: Primitive representation upstream — Stage 2 결과물이 main, CityGML 은 샘플 응용

이 선택이 **전체 논문 구조** 를 바꿈 (Phase 2 가 main 인지 supporting 인지).

### III.4 메커니즘 설계 자체에 대한 의문 생김 (NEW — critical)

지금까지는 "메커니즘 1/2 의 설계는 유효" 라고 가정했는데 Phase 2 에서 재검토 필요:

#### L_mutual 의 이중 영향
- Stage 2 에선 Wall 수직화 효과 확실
- 하지만 **Stage 3 val3dity 회귀** 로 CityGML 품질은 오히려 악화 (gable 54→25%, flat 44→32%)
- 현재 **이 회귀의 메커니즘 불명**. 추정 후보 (증거 약함):
  - Semantic 재분류 효과가 Stage 3 clustering 교란
  - n_i 만 수정하고 c_i 는 photo 에 따름 → 평면 d 값 불일치
  - 21% 미정리 wall primitive 의 noise
- **스케치 수정**: "L_mutual 이 Stage 2 primitive 를 개선 → Stage 3 품질 향상" 이 **단순 인과 아님**. 알고리즘 조합에 따라 반대 효과 가능.

#### L_structure 의 Phase 2 효과 부재
- Phase 1: σ_normal_intra −45%
- Phase 2: +1% (거의 없음)
- 원인 불명. w_structure 문제 아님 확인. Grouping 결과 자체 조사 필요.
- **스케치 수정**: L_structure 의 효과가 **데이터에 강하게 의존**. "복잡 합성 / 실 데이터 에서 효과 확인 필요" 로 명시.

#### Both 의 시너지 부재
- 설계 가설: L_mutual + L_structure 동시 작용으로 **순환 효과**
- 실측: L_mutual 지배, L_structure 는 Mutual 회귀를 **부분 상쇄** 할 뿐. Additive synergy 없음.
- **스케치 수정**: "순환 효과" 가설은 **미입증**. "L_structure 가 L_mutual 의 side effect 를 완화" 정도로 약화된 claim.

### III.5 Data transferability + Sequential baseline (기존과 동일)

- Synthetic → Real transferability 측정 프레임 필요 (Phase 3 이전에)
- Sequential baseline (MVS + RANSAC + convex) 측정 필요 — 우리 방법의 우위 정량화 전제

---

## Part IV. 열린 질문 (이번 업데이트에서 확장)

### IV.1 기존 질문들 (여전히 유효)

1. 합성 PSNR 40 vs 실데이터 기대 22-28 의 비교 프레임
2. 4 조건 ablation 의 충분성
3. 성수동 vs Phase 2 데이터 스펙 일관성
4. Real vs synthetic transferability 정량화

### IV.2 이번 업데이트로 추가된 질문들

5. **L_mutual 이 단순 건물 val3dity 에서 회귀하는 정확한 메커니즘은?** — 진단 실험 D1 로 해소 예정
6. **L_structure 가 Phase 2 에서 효과 부재인 이유?** — 진단 실험 D2 로 해소 예정
7. **Stage 3 6-step 중 어느 step 이 각 조건의 차이를 만드는가?** — 진단 실험 D3 로 해소 예정
8. **Stage 3 알고리즘 (convex) 의 76.3% ceiling 을 올리는 것이 연구 우선순위인가?** — 포지셔닝에 따라 다름 (틀 A 라면 필수, 틀 B 라면 선택)
9. **"순환 효과" 라는 메커니즘 설계 가설을 Phase 2 결과로 지지 가능한가?** — 현재 미지지. 수정 필요.
10. **Phase 3 (real 성수동) 의 역할**: main contribution vs supporting validation?

---

## Part V. 현재 남은 작업 (Phase 2-2 이후)

### 완료 (D1-D4 모두 완료)

| 작업 | 상태 | 산출물 |
|---|---|---|
| D1 (Mutual regression 원인) | ✓ | fig_d1_bid002.png, fig_d1_bid022.png |
| D2 (L_structure grouping) | ✓ | fig_d2_structure_grouping.png |
| D3 (Stage 3 6-step breakdown) | ✓ | fig_d3_bid{2,22,6,21}_steps.png |
| D4 (Wall 법선 공간 패턴) | ✓ | fig_d4_baseline_wall_tilt.png |
| Phase 2-2 REPORT v3 (진단 통합) | ✓ | results/phase2_ablation_citygml/REPORT.md |

### 단기 (~2 주)

| 작업 | 산출물 |
|---|---|
| **연구 포지셔닝 결정** (틀 A/B/C) | claude-web 논의 결과 반영 |
| 학습 중 gradient norm 측정 (D2 가설 D 검증) | 추가 분석 |
| Sequential baseline 측정 (MVS+RANSAC+convex) | joint vs sequential 정량화 |

### 중기 (1-2 개월, 포지셔닝에 따라)

- Sequential baseline 측정 (MVS + RANSAC + convex) — joint vs sequential 정량화
- Stage 3 알고리즘 개선 (PolyFit 완성 or City3D 통합)
- Phase 3 (real 성수동 UAV) 데이터 준비 + 학습
- Phase 2 의 "secondary validation" vs "main contribution" 으로 위상 정리

### 메커니즘 재학습 (선택적, 포지셔닝 후 결정)

- L_mutual 수정 (center consistency 항 추가, tolerance 완화) + 재학습 1 회
- L_structure grouping 알고리즘 개선 + 재학습 1 회
- 단, **현 진단 전** 재학습은 같은 문제 반복 우려 → D1-D4 결과 먼저

---

## Part VI. 이 문서가 스케치에 반영될 때 제안

1. **스케치의 "평가 지표" 섹션 확장** — 3 축 (렌더링 / primitive / CityGML) 으로 분리
2. **"Stage 3 알고리즘 선택의 명시화" 섹션 신설** — convex/2.5D/PolyFit/City3D 트레이드오프
3. **"연구 포지셔닝 선택지 (틀 A/B/C)" 섹션 신설** — 박사 논문 구조 결정
4. **"메커니즘 설계 재검토" 섹션 신설** — Phase 2 결과가 원 설계 가설을 일부 뒤흔듦
5. **"열린 질문" 확장** (IV.2 새 질문 포함)
6. **"Synthetic → Real transferability"** 는 기존 유지
7. **데이터 설계 원칙** (Pix4D 표준, v1/v2 교훈) 은 기존 유지

### 방법론 본문 수정 제안

- **메커니즘 1**: 설계 자체는 유지. 단 "n_i 수정이 c_i 에도 영향 줘야" (center consistency) 추가 필요 가능성
- **메커니즘 2**: 설계는 유지, 단 grouping 알고리즘 의존성 명시. Phase 2 에서 효과 부재 → 데이터 의존성 반영 필요
- **"순환 효과"**: Phase 2 에서 미지지됨. claim 을 **"각 메커니즘이 독립적으로 서로 다른 축 개선, Both 에서 공존"** 으로 약화

---

**부록**: 관련 문서
- `docs/CLAUDE.md` — 프로젝트 규칙 + 진행 체크리스트
- `docs/RESEARCH_CONTEXT.md` — 기술 맥락 상세
- `docs/EXPERIMENT_PLAN.md` — Phase 별 실험 순서
- `docs/RESEARCH_STATUS.md` — 연구 포지셔닝 재검토 (A/B/C 틀)
- `results/phase2_ablation_citygml/REPORT.md` — Phase 2-2 상세 결과
- `results/phase2_synthesis/REPORT.md` — Phase 2-1 데이터 파이프라인
