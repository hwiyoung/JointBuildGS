# 도시 규모 건물 3D 복원 — Claude Web 브리핑 v5

> v4(2026-04-25) 이후 작업: G2(surface 단위 grouping) 함수 구현 + 검증, 그 과정에서 σ_coplanar 1.84m 라는 본질적 문제 발견 → 추가 분석 결과 **Phase 2 학습은 매우 잘 됐으나 Stage 3 알고리즘 자체에 본질적 결함**으로 결론 수정. 이 문서는 일련의 측정과 *여러 차례 수정한 결론*을 정직하게 기록.

## 0. 용어 정리

| 약어 | 풀어쓴 표현 |
|---|---|
| **G1** | 기존 grouping — 5cm voxel + 12방향 bin (~154 patch/건물) |
| **G2** | 신 grouping — 2m coarse voxel + cell 단위 union-find (~7 surface/건물) |
| **C3a** | L_photo + L_normal이 이미 normal 정렬해 L_structure 추가 작용 못 함 |
| **C3b** | G1 patch가 동질적이라 L_structure가 patch 내부 smoothing에 그침 |
| **C3c** | cycle 4 고리 모두 약함 |
| **C4** (폐기) | baseline 손실로 cm 응집 불가 가설 — Phase 1 데이터로 반증됨 |
| **cluster_primitives** | Stage 3의 surface clustering (cos>0.92 hierarchical + spatial_split + merge tiny) |
| **process_building** | Stage 3의 한 건물 polytope 추출 (cluster_primitives 사용 + half-space intersection) |

---

## 1. 한 줄 요약

**Phase 2 Stage 2 학습은 매우 잘 됨** (PSNR 40+, mIoU 0.97, F1@0.5m 0.97, G1 σ_coplanar 2.6mm). **본질적 문제는 Stage 3 알고리즘**: cluster_primitives의 방향 기반 그룹핑 + spatial_split 실패 → process_building의 polytope이 GT의 25% 만 커버 → Hausdorff 11.5m.

---

## 2. 진행한 측정 항목 (시간순)

기존 보고서 mining + 새 측정:

### 2.1 G2 sanity (P1-2 단계)
- median 7 그룹/건물, 91% primitive grouped, 26초 (CPU)
- ✓ G1 154 → G2 7 압축 성공

### 2.2 G2 시각적 검증 + GT overlay
- 작은 깨끗한 surface (g206): face polygon 96% 커버 ✓
- 큰 그룹 (g386 910 prims): 18m × 10m × 11m 범위 spread (over-merge)
- floater 그룹 (g204): GT face와 무관

### 2.3 σ_coplanar 1.84m 발견 (Phase 2 Mutual)
- cluster_primitives 그룹 단위 측정 → 1.84m
- *처음에는 primitive 분포 자체의 문제로 해석* → 후속 측정에서 반증

### 2.4 Phase 1 mining
- σ_coplanar 7.2-9mm (cm 단위 응집)
- σ_normal_intra 1.4° (Phase 2 14.7° 대비 10배 작음)
- L_structure 효과: σ_normal_intra **−45%** (Phase 2는 +1% 부재)
- F1@0.5m 0.998-0.999 (분야 평균 이상)
- mIoU 0.625-0.640

### 2.5 Phase 1 cycle 4고리 측정
- Loop 1 (loss magnitude ratio): **L_mutual_vert : L_structure_na = 84 : 1** (Phase 2 135:1과 비슷한 자릿수)
- Loop 2-4: TB scalar 부족, 미측정
- ratio가 작아도 σ_normal_intra −45% 효과 → 절대값과 normal_cos 수렴 정도가 진짜 차이

### 2.6 Perturbation test (광도 redundancy 가설)
| Shift | Phase 1 ΔPSNR | Phase 2 ΔPSNR | 비율 |
|---|---|---|---|
| 0.10m | −6.45 dB | −0.85 dB | 7.6× |
| 0.50m | −7.83 dB | −5.00 dB | 1.6× |
| 1.00m | −7.81 dB | −7.50 dB | **1.04×** |
| 2.00m | −9.35 dB | −10.12 dB | 0.92× |

→ **sub-meter (cm-dm) 단위에선 Phase 2가 photo에 둔감, 1m 이상은 둘 다 비슷**. C3a (광도 redundancy)는 sub-meter 영역에 한정 입증.

### 2.7 Phase 2 G1 vs G2 vs cluster_primitives σ
| 그룹 단위 | Phase 1 (Both) | Phase 2 (Both) |
|---|---|---|
| G1 (5cm voxel) | 7.5 mm | **2.6 mm** ⭐ |
| cluster_primitives (Stage 3) | 7-9 mm | **1840-2010 mm** |
| G2 (2m + union-find) | 459 mm | 787 mm |

**Phase 2 G1은 Phase 1보다 *더 좋음* (mm 단위 응집)**. σ_coplanar 1.84m는 cluster_primitives의 over-merge로 발생, primitive 분포 자체의 문제 아님.

### 2.8 Phase 2 F1@0.5m 측정
| 조건 | F1@0.5m | F1@1.0m |
|---|---|---|
| Baseline | 0.972 | 0.992 |
| Mutual | 0.972 | 0.989 |
| Structure | **0.980** | 0.994 |
| Both | 0.974 | 0.992 |

→ Phase 1 0.999 대비 살짝 낮지만 **분야 표준에서 매우 양호**. primitive 기하 학습 성공.

### 2.9 Phase 2 mIoU 측정 (eval_stage2_primitives.py에 누락된 항목 보완)
| 조건 | mIoU | Roof | Wall | Terrain | Pixel Acc |
|---|---|---|---|---|---|
| Baseline | 0.972 | 0.989 | 0.938 | 0.988 | 0.991 |
| Mutual | 0.969 | 0.988 | 0.934 | 0.987 | 0.990 |
| Structure | 0.971 | 0.989 | 0.937 | 0.988 | 0.991 |
| Both | **0.973** | 0.987 | **0.942** | 0.989 | 0.991 |

→ **Phase 2 mIoU 0.97** (Phase 1 0.63 대비 *훨씬* 좋음 — Phase 1은 rule-GT artifact). semantic 학습 매우 우수.

### 2.10 cluster_primitives 파라미터 sweep (over-merge 가설 검증)
bid=1, 6, 21에 cos_thresh 변경:
| cos_thresh | n_groups/bldg | σ_normal | σ_coplanar |
|---|---|---|---|
| 0.85 (default) | 8.0 | 14.6° | 2050mm |
| 0.99 | 84.2 | 8.8° | 2144mm |
| 0.999 | 857.2 | 0.42° | 980mm |

→ **cos thresh 강화로도 σ_coplanar 안 줄어듦**. 단순 normal 분리 외 spatial 분리가 dominant 문제.

### 2.11 Phase 2 단일 건물 polytope 시각화 (bid=21)
- GT bbox: 13m × 17m × 10m = 2210 m³ box
- Polytope bbox: 5m × 6m × 6m = 188 m³ box
- Polytope volume: 49.5 m³
- **GT 건물의 25%만 커버** → Hausdorff 11.5m의 직접 원인

### 2.12 cluster_primitives 클러스터 공간 분포 시각화 (bid=21)
- 10 clusters 색상 구분 결과 → **각 cluster가 공간적으로 응집되지 않고 건물 전체에 섞임**
- 즉 cluster_primitives는 *방향 기반*이라 같은 normal의 primitive를 건물 전체에서 모음
- spatial_split은 plane_d gap을 찾아 분리해야 하는데 Phase 2 dense primitive에 실패

### 2.12b cluster × GT face cross-tab (over-merge 직접 입증)
**ALL bbox primitives** (Stage 3 실제 입력) 2011개에 cluster_primitives 적용:
```
cluster  0 (Roof,  77 prims)  100% off-surface — pure noise group
cluster  4 (Roof, 256 prims)  face 32 191/256 (75%) — clean ✓
cluster  8 (Wall, 166 prims)  faces 3+19+26 — mild over-merge
cluster 12 (Wall, 415 prims)  faces 6, 14, 19, 20, 23 (5+ GT 벽면 혼재) ← 결정적 over-merge 증거
```
→ **cluster_primitives가 *물리적으로 구별되는* GT face들을 한 cluster로 합침**.
- cluster 12: face 6 (80m²) + face 23 (65m²) + face 20 (10m²) + ...
- 모두 비슷한 normal 방향, plane_d gap이 dense primitive로 마스킹 → spatial_split 실패
- 추가로 ~25-65%가 off-surface noise → rep_plane 부정확

### 2.13 Phase 1 → Stage 3 (8.1) — 평가 한계
- 30m × 30m × 50m region (multi-building) → 작은 polytope (multi-building 이슈)
- 8m × 8m × 20m region → vol 2.26 m³
- 둘 다 manifold + watertight (boundary 0, nonmanifold 0)
- **Phase 1은 building instance 분리 자체가 없음** → Stage 3 평가가 본질적으로 부적합
- 따라서 Stage 3 결함 결론은 **Phase 2 단일 건물 polytope 25% coverage**가 직접 근거

### 2.14 Cycle Loop 4 측정 (Phase 1 TB)
| run | n_groups mean | CV | Δstep mean | Δstep max |
|---|---|---|---|---|
| Phase 1 Structure | 248k | 0.19% | 2.62 | 648 |
| Phase 1 Both | 226k | 0.91% | 6.99 | 902 |
| Phase 2 (CLAUDE.md §14.4) | 167k | 2.01% | ~0.007% | (small) |

→ Phase 1, Phase 2 둘 다 group churning 약함. **Loop 4가 차이의 원인 아님**. 차이는 Loop 1 magnitude + normal_cos 수렴 정도.

### 2.15 Sub-1m perturbation 정량 분석
| Shift | Phase 1 ΔdB | Phase 2 ΔdB | P1/P2 sensitivity |
|---|---|---|---|
| 0.10m | −6.45 | −0.85 | **7.58×** |
| 0.30m | −7.42 | −3.29 | 2.25× |
| 0.50m | −7.83 | −5.00 | 1.57× |
| 1.00m | −7.81 | −7.50 | 1.04× |
| 2.00m | −9.35 | −10.12 | 0.92× |

→ **광도 redundancy는 sub-meter (cm-dm) 영역에 한정 입증**. L_structure의 merge_d_tol=0.5m가 이 영역에 해당 → sub-meter photo 둔감 → L_structure 작동 어려움 (메커니즘 명확).

---

## 3. 진단의 변천 (정직한 기록)

| 가설 (제기 순) | 검증 결과 | 최종 |
|---|---|---|
| "σ_coplanar 1.84m는 primitive가 흩어진 결과" | G1 단위 측정 결과 mm | **반증** — cluster_primitives over-merge가 원인 |
| "광도 손실 redundancy로 primitive 응집 안 됨" | Perturbation 1m → -7.5dB Phase 2도 큰 폭 | **부분 반증** — sub-meter만 redundancy |
| "Phase 2 학습 부족" | F1 0.97, mIoU 0.97, G1 σ 2.6mm | **반증** — 매우 잘 됨 |
| "G2가 Phase 2 해결" | G2 σ 787mm (chaining) | **부정** — G2도 chaining 문제 |
| "Stage 3 OK" | Phase 1+2 polytope 시각화 | **부정** — coverage 부실 |
| "Cluster_primitives over-merge" | Cluster 시각 + sweep | **확정** — 방향 기반 + spatial 분리 실패 |

**솔직한 평가**: 이 측정 sequence에서 여러 가설이 확립되었다가 후속 데이터로 반증되었습니다. 매 단계 시각/정량 검증 없이 단일 metric으로 결론짓는 게 위험함을 보여줌.

---

## 4. 최종 진단

### 4.1 Stage 2 학습 quality (양호)

| 지표 | Phase 1 | Phase 2 | 비고 |
|---|---|---|---|
| PSNR | 20.5 | 40.4 | Phase 2 더 좋음 |
| mIoU | 0.63 | **0.97** | Phase 2 훨씬 좋음 (Phase 1은 rule-GT artifact) |
| F1@0.5m | 0.999 | 0.97 | 둘 다 매우 양호 |
| G1 σ_coplanar | 7-9mm | **2.6-8.2mm** | 둘 다 cm 단위 응집 ✓ |
| G1 σ_normal | 1.4° | 1.3° | 둘 다 정렬 양호 ✓ |

→ **Phase 2도 primitive 단위 학습은 매우 잘 됨**.

### 4.2 L_structure Phase 2 효과 부재 (C3a 메커니즘)

- normal_cos: Phase 1 0.68 → Phase 2 0.98 (이미 정렬 끝)
- L_structure 의 normal_align 항 (1−|n·n_k|)² gradient ≈ 0
- 추가로 sub-meter 단위에서 photo가 둔감 → primitive가 살짝 흔들려도 PSNR 거의 안 변함

### 4.2b "두 메커니즘 cycle"은 입증되지 않음 — thesis 핵심 claim 재검토 필요

**구분이 필요**:

| 개념 | Phase 1 | Phase 2 | 결론 |
|---|---|---|---|
| **L_structure 단방향 효과** (Loop 1, 단발성) | σ_normal_intra **−45%** ✓ | +1% (효과 부재) | Phase 1에서만 작동 |
| **4-loop 동적 cycle** (전체 순환) | Loop 4 CV 0.19% (그룹 정적) | Loop 4 CV 2.01%, change 0.007% | 양쪽 다 안 작동 |

**Phase 1 σ −45%의 진짜 메커니즘**: 그룹은 거의 고정된 채 (Loop 4 churn 0.19%), 그 *고정된* 그룹 안에서 L_structure가 n_i를 정렬한 단발성 효과. **"cycle"이 아니라 "단발성 alignment"**.

→ **thesis "cycle of feedback" claim은 데이터로 *반증***됨. 두 메커니즘은 *각자 작동*하나 *상호 동적 피드백 없음*:
- L_mutual: Wall vert 28→79% ✓ (작동)
- L_structure: Phase 1에서 단발성 σ_normal alignment ✓ (작동)
- 두 메커니즘이 *iteration 단위로 상호 영향* → ✗ (반증)

Thesis 재구성: "cycle" → "두 독립 메커니즘 결합" 으로 약화 필요.

### 4.3 Stage 3 알고리즘의 본질적 결함

```
입력 (Phase 2): G1 σ 2.6mm cm 단위 응집된 primitive
           ↓
[Stage 3 step 2] cluster_primitives (cos>0.92 + spatial_split)
   - 방향 기반 클러스터링: 같은 normal primitive를 건물 전체에서 모음
   - spatial_split (plane_d gap 1m): Phase 2 dense primitive에 gap 안 생김 → 실패
   - 결과: cluster들이 공간적으로 섞임. 각 cluster의 rep plane이 부정확
           ↓
[Stage 3 step 3] 대표 평면 fit (averaged from scattered primitives)
   - 부정확한 rep_n, rep_d
           ↓
[Stage 3 step 4] half-space intersection
   - 부정확한 plane들의 교차 → degenerate polytope
           ↓
출력: GT의 25% 만 커버하는 작은 polytope, Hausdorff 11.5m
```

### 4.4 G1, G2가 이 문제를 못 잡는 이유
- G1 (5cm voxel): cluster 단위가 너무 작음 (patch). 그 자체로는 surface 단위 안 됨
- G2 (2m + union-find): chaining issue로 σ_coplanar 0.5-1m. surface 정확도 부족
- **둘 다 *Stage 3 cluster_primitives의 다음 단계 입력으로 적합하지 않음***

---

## 4.5 Stage 3 입력 변경 시도 결과 (2026-04-27 추가)

세 가지 접근으로 Stage 3 직접 개선 시도. 모두 *각자 다른* 한계.

### A1: G2 → Stage 3 (P1-2 missing step)
| bid | G2 v3d | default v3d |
|---|---|---|
| 1 | ✗ | ✓ |
| 2 | ✓ | ✓ |
| 6 | ✗ | ✗ |
| 21 | ✗ | ✗ |
| 22 | ✗ | ✓ |
| **합** | **1/5** | 3/5 |

→ G2 chaining (σ 787mm)이 cluster_primitives보다 나쁜 rep_plane → polytope 부정확.

### A2: RANSAC plane → Stage 3
| bid | RANSAC | G2 | default |
|---|---|---|---|
| 1 | ✗ | ✗ | ✓ |
| 2 | ✗ | ✓ | ✓ |
| 6 | **✓** | ✗ | ✗ |
| 21 | **✓** | ✗ | ✗ |
| 22 | ✗ | ✗ | ✓ |
| **합** | 2/5 | 1/5 | 3/5 |

→ RANSAC이 *복잡 건물 (6, 21)*에선 default 능가. *단순 건물 (1, 22)*에선 부족. 각자 강점 다름.

### C1: 2DGS marching cubes → mesh
- F1@0.5m: **0.22** (렌더 depth 기준 0.97과 매우 다름)
- pred→GT mean 32m (도시 전체 통합으로 노이즈 큼)
- 단순 TSDF는 건물 분리/구조화 안 됨 → 후처리 필요

**종합**: *명확한 winning approach 없음*. GT face centroid 96% 천장에 누구도 근접 못 함.

---

## 5. 함의 및 노선 결정

### 5.1 Phase 2 재학습은 의미 없음
Phase 2 primitive level은 이미 cm 단위로 잘 됐음. L_structure 추가 학습 시 σ_coplanar이 mm에서 더 줄어들 여지 적음 (gradient 부재). **Phase 2 재학습 → CityGML 품질 개선 가능성 낮음**.

### 5.2 Stage 3 알고리즘 재설계가 우선
현 cluster_primitives + half-space intersection 파이프라인이 본질적 결함:
- 방향 기반 클러스터링 → 공간 정합 실패
- 부정확한 rep plane → 부정확한 polytope

대안:
- **(A) Plane_d 기반 1D 클러스터링 + spatial CC** (algorithm C, 이전 G2 후보):
  rep planes를 plane_d 따라 1D 클러스터링 (chaining 없음) + 공간 CC로 분리.
  cluster_primitives의 spatial_split 실패 문제를 우회.
- **(B) Region growing on rendered normal map**:
  primitive 단위가 아니라 *렌더된 픽셀 단위*에서 region growing → instance segmentation처럼 surface 분리.
- **(C) GS → mesh → PolyFit**:
  Phase 2 mesh quality가 좋다면 (F1@0.5m 0.97 기반 가능성 있음) PolyFit/City3D로 변환.
  thesis novelty는 joint optimization 자체에 있음. 출력 경로 변경은 novelty 약화 아님.

### 5.3 Phase 3 (real UAV) 의의
- Phase 1과 Phase 2가 Stage 3에서 비슷하게 한계 보임
- Phase 3에서도 같은 Stage 3 쓰면 같은 문제 가능성
- **Stage 3 재설계 후 Phase 3 가야** thesis 검증 의미 있음

### 5.4 thesis novelty 위치 재정의 (모든 측정 종합)

**원래 claim**:
1. Joint optimization (메커니즘 1+2)
2. **cycle of feedback** (두 메커니즘 동적 상호작용)
3. → **직접 CityGML 출력**

**수정된 claim (데이터 기반)**:
1. **Joint optimization으로 cm 단위 응집 + 의미론 정확 학습 가능** ✓ — 강한 contribution
   - Phase 2 G1 σ_coplanar 2.6mm
   - Phase 2 mIoU 0.97
   - Phase 2 F1@0.5m 0.97
2. **두 메커니즘이 *각자* 작동** ✓ (Wall vert 28→79%, σ_normal -45% Phase 1)
3. **"Cycle"은 데이터로 반증** ✗ (Loop 4 churn ~0, f_i argmax change 0.45%)
   - "두 메커니즘 결합"으로 약화
4. **직접 CityGML 출력은 한계** △
   - 알고리즘 천장 96% (sparse + 정확한 입력 한정)
   - 우리 출력 55% (입력 분포 mismatch)
   - 시도한 입력 변경 (G2, RANSAC, mesh) 모두 부족
   - **출력 경로 변경 (mesh) 또는 별도 plane proposal 알고리즘 발전 필요** — *future work*

### 5.5 어떤 contribution을 살릴 수 있는가

| Contribution | 입증 상태 | 강도 |
|---|---|---|
| Joint geometry-semantic optimization | 입증 | **강** |
| L_mutual: 도메인 규칙 → primitive 정합 | 입증 | **강** |
| L_structure: surface 단위 정렬 (단발성) | Phase 1 입증, Phase 2 photo redundancy로 부재 | **중** |
| 두 메커니즘 동적 cycle | 반증 | **약** (재정의 필요) |
| 직접 CityGML 출력 | 한계 | **약** (future work) |

**현실적 thesis 위치**:
- *Primary contribution*: "Joint optimization으로 의미론과 기하를 cm 단위 정확도로 동시 학습" (입증)
- *Secondary contribution*: "두 도메인 손실 (intra/inter primitive)이 *각자* 효과적" (입증)
- *Limited contribution*: "강한 photo 환경에선 inter-primitive 손실 효과 제한적" (boundary 정의)
- *Future work*: "구조화된 출력 (CityGML) 추출은 별도 연구 과제" (한계 명시)

cycle claim과 직접 CityGML claim은 thesis에서 약화 또는 future work로 이관.

---

## 6. Stage 3 재설계 — 참고 알고리즘 후보

현 cluster_primitives + half-space intersection 결함 → 대체 후보. **이미 시도한 것 vs 새로 검토할 것** 구분:

### 6.1 Plane 후보 개선 (cluster_primitives 대체)
| 옵션 | 상태 |
|---|---|
| (a) RANSAC 기반 다중 plane 추출 | **시도됨** — legacy/planarsplat_ref/. 비슷한 한계 (plane 후보 over/under) |
| (b) Region growing on rendered normal map | **미시도** — 픽셀 단위 instance segmentation, 새 후보 |
| (c) G2 + 후처리 (chaining 잡기) | **G2까지만 시도** — 후처리는 미시도 |
| (g) DBSCAN/HDBSCAN on plane_d 1D | **미시도** — spatial_split보다 robust gap detection |
| (h) Mean-shift on (n, plane_d) 5D space | **미시도** — soft clustering |

### 6.2 후속 알고리즘 (process_building 대체)
| 옵션 | 상태 |
|---|---|
| (d) PolyFit (Nan & Wonka 2017) | **시도됨, GT 입력에서도 *실패*** — val3dity 0%, watertight 안 닫힘. v4 보고서 §7. Stage 2 출력에 적용해도 더 잘 될 가능성 낮음 |
| (e) KSR/KSR-42 (Bauchet & Lafarge 2020) | **미시도** — 구현 복잡 (수일~주), 작동 보장 없음 |
| (f) City3D (Huang 2022) | **미시도** — building 도메인 특화 (footprint+roof type 가정), 데이터셋 호환 미지 |

### 6.3 출력 경로 변경 백업
- **2DGS native marching cubes**: 미시도. density field → mesh → PolyFit
- **SuGaR, PGSR**: 별도 모델 학습 필요

### 6.4 솔직한 평가: 검증된 winning approach 없음

§6.1, 6.2의 후보 중 *작동 검증된 것 없음*:
- PolyFit이 가장 직접 적용 가능했는데 GT에서도 실패
- KSR/City3D는 구현 부담 크고 작동 보장 없음
- (b)/(g)/(h)는 사실상 추측

**즉 Stage 3 재설계는 *연구 수준의 도전*임**. 알고리즘 swap 으로 단기 해결 안 됨.

### 6.5 더 실현 가능한 두 노선

1. **출력 경로 변경 (mesh)**: 2DGS native marching cubes → mesh → 기존 mesh-to-CityGML.
   - Phase 2 mesh quality 좋다면 가능 (F1@0.5m 0.97 → mesh 좋을 가능성)
   - 그러나 mesh-to-CityGML도 별도 난제 (PolyFit 같은 후처리)

2. **Stage 2 자체에 surface-aware regularization 추가**:
   - 예: 인접 primitive 사이 plane_d gap 발생하도록 손실 추가
   - cluster_primitives의 spatial_split이 작동할 수 있도록 입력 분포 변경
   - Phase 2 σ_coplanar이 줄어들 수 있는 추가 손실

3. **thesis claim 재정의**: "cycle"을 "두 독립 메커니즘 결합"으로 약화 + 출력 경로는 별도 contribution으로 분리

---

## 7. 미해결 질문 (Claude Web 토론용)

1. **Stage 3 재설계 우선순위**: 6.1 + 6.2의 어느 조합?
2. **Phase 3 (real UAV)에서 Stage 3는?** Phase 1과 비슷할지, Phase 2와 비슷할지 미지
3. **thesis 재구성**: "joint opt → primitive cm 응집 입증" + "출력 경로는 별개" 로 분리할 수 있나?
4. **cycle Loop 2/3 측정**: intermediate ckpt 또는 추가 hook 필요. 진행 가치 있나?
5. **Phase 2 재학습 의미**: G1 σ 2.6mm가 더 줄어들 여지 거의 없음. 새 손실로 σ_coplanar 줄일 수 있나? (그러나 cluster_primitives over-merge가 진짜 문제)

---

## 8. 핵심 수치 요약

### Stage 2 (Phase 2 Both)
- PSNR: 40.40
- mIoU: **0.973** (Roof 0.987, Wall 0.942, Terrain 0.989)
- F1@0.5m: **0.974**, F1@1.0m: 0.992
- G1 σ_normal: **1.30°**, σ_coplanar: **2.6 mm**
- cluster_primitives σ_coplanar (Stage 3 단위): 2.0m
- G2 σ_coplanar: 787mm

### Phase 1 (Both)
- PSNR: 20.6
- mIoU: 0.625
- F1@0.5m: 0.999
- σ_normal: 0.91°, σ_coplanar: 7.5mm

### Stage 3 (Phase 2 Mutual)
- val3dity: 48.9-55%
- face IoU: 0.20-0.24
- Hausdorff: **11.5m** (GT 16m 건물 대비 ~70%)
- semantic accuracy: 20.6%
- bid=21 polytope coverage: GT의 **25%**

### Perturbation (광도 redundancy 검증)
- 0.1m shift: Phase 1 −6.45dB / Phase 2 −0.85dB (7.6× 비대칭)
- 1.0m shift: Phase 1 −7.81dB / Phase 2 −7.50dB (대칭)
- → sub-meter 영역에서만 Phase 2 photo 둔감

---

## 9. 코드 위치

```
src/stage2/grouping.py
├── group_primitives()           기존 G1
└── group_primitives_g2()        신 G2

src/stage3/clustering.py
├── cluster_primitives()         **본질적 결함 — 방향 기반 + spatial_split 실패**
└── _spatial_split()             plane_d gap detection (Phase 2에 실패)

src/stage3/building_instance.py
├── process_building()           half-space intersection → polytope

scripts/phase2_synthesis/
├── perturb_psnr_test.py        광도 redundancy 검증
├── eval_f1_geometry.py          F1@0.5m, F1@1m
├── eval_miou.py                 mIoU
├── inspect_cluster_primitives.py 클러스터 진단
├── sweep_cluster_params.py      cos_thresh sweep
├── test_stage3_strict_cluster.py polytope 결과 검증

scripts/phase1_analysis/
├── analyze_g1_vs_g2.py         G1 vs G2 σ 비교
├── cycle_4loop.py              Loop 1 측정
└── test_stage3_on_phase1.py    Stage 3 on Phase 1 region

results/phase2_ablation_citygml/_cluster_inspect/
├── bid21_polytope_vs_gt.png    Phase 2 polytope vs GT (25% coverage)
└── bid21_clusters.png          cluster_primitives 공간 혼재 시각화

results/phase1_analysis/
├── perturb_test/perturb_bid21.json  Perturbation 결과
├── stage3_test/polytope_*.png   Phase 1 Stage 3 출력
└── g1_vs_g2_summary.json
```

---

## 10. v3 → v4 → v5 변화 요약

| 항목 | v3 | v4 | v5 |
|---|---|---|---|
| 본질적 진단 | "C3a/b/c — L_structure 효과 부재" | "G2로 surface 단위 grouping" | **"Stage 3 cluster_primitives 본질적 결함 + Phase 2 학습은 잘 됨"** |
| Phase 2 평가 | 효과 미미 | 재학습 권고 | **재학습 의미 없음. Stage 3 재설계 우선** |
| Stage 3 평가 | 정상 가정 | 인터페이스 정렬 | **Stage 3 알고리즘 자체 결함 — polytope 25% coverage** |
| Cycle 가설 | 미입증 | Phase 2 부재 | sub-meter 단위 작동 (Phase 1 입증, Phase 2 photo redundancy로 미발현) |
| Output 경로 | 직접 CityGML 핵심 | mesh→CityGML 백업 | **GS→mesh→PolyFit 등 대안 진지 검토** |
| 다음 단계 | Track 1 | G2 + 재학습 | **Stage 3 재설계 + 후 Phase 3** |
| thesis 위치 | 약화 가능 | G2 결과 의존 | **"primitive cm 응집은 입증, 출력 경로는 별개 문제"로 재정의** |
