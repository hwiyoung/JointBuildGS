# 도시 규모 건물의 구조적 3D 복원을 위한 기하-의미론 공동 최적화

## 프로젝트 개요
미분 가능 렌더링 기반 평면 프리미티브(2DGS) 위에 건물 도메인 지식과 면 단위 구조 인식을 통합하여, 건물의 재구성과 구조화를 공동 최적화하는 박사 연구.

공동 최적화 두 수준:
- **Intra-primitive (메커니즘 1, L_mutual):** 개별 프리미티브의 도메인 규칙 기반 상호 교정
- **Inter-primitive (메커니즘 2, L_structure):** 프리미티브 간 구조적 일관성 제약

## Base: gsplat + 2DGS
gsplat (pip install gsplat)을 렌더링 라이브러리로 사용. fork가 아닌 의존성.
우리 코드(model, loss, grouping, train)가 주체이고, gsplat은 렌더링 함수 제공.
gsplat 선정 이유: N-D feature 네이티브 렌더링(semantic head CUDA fork 불필요), 모듈식 구조, Apache-2.0 라이선스, 활발한 개발.

## 상세 문서
- `docs/EXPERIMENT_PLAN.md` — 실험 순서, 프롬프트, REPORT 템플릿
- `docs/RESEARCH_CONTEXT.md` — 연구 배경, 파라미터, 손실 함수 상세

## 파이프라인
- **Stage 1**: SfM/MVS + 2D Segmentation + Gravity 추정
- **Stage 2**: 구조 인식 공동 최적화 (gsplat/2DGS + L_mutual + L_structure)
- **Stage 3**: CityGML 변환

## 프리미티브 (G_i)
| 변수 | 차원 | 의미 |
|------|------|------|
| c_i | (N,3) | 중심 |
| n_i | tangent 외적 | 법선 (t_u × t_v) |
| s_i | (N,2) | in-plane scale |
| f_i | (N,4) | 의미론 (BG/Roof/Wall/Terrain) |
| color_i | SH | 색상 |

## 손실 함수
```
L = L_depth + L_normal + λ_nc·L_nc + λ_s·L_sem + λ_p·L_photo + λ_m·L_mutual + λ_str·L_structure

L_depth  → c_i              MVS depth L1
L_normal → n_i              MVS normal cosine
L_nc     → n_i, c_i         렌더링normal ≈ depth유도normal
L_sem    → f_i              CrossEntropy (ignore_index=0)
L_photo  → all              L1 + SSIM
L_mutual → n_i, f_i, c_i(h) intra-primitive 도메인 규칙
L_structure → n_i, c_i      inter-primitive 구조 정렬
```

## 메커니즘 1: Intra-primitive (L_mutual)
- L_vert: 벽 법선 → 수평(gravity에 수직)
- L_slope: roof가 벽처럼 수평이면 penalty
- L_horiz: terrain 법선 → 수직
- L_height: roof > terrain (높이)
- 핵심: p_c × 기하 오차의 곱 → 양방향 gradient (f_i ↔ n_i)
- Gradient: n_i, f_i 양방향. c_i(L_height 높이만). s_i 없음.

## 메커니즘 2: Inter-primitive (L_structure)
- 매 T iter 그룹핑: 동일 class + 법선 유사 + 공간 근접
- L_normal_align: 같은 그룹 법선 → 대표 법선 (n_i gradient, n_k detach)
- L_coplanar: 같은 그룹 중심 → 대표 평면 위 (c_i gradient, n_k/d_k detach)
- L_coverage: 후보 (densification 대비 검증)
- **f_i에 직접 gradient 없음** (그룹 할당 = argmax, 이산 연산)
- f_i 교정은 메커니즘 1이 담당. 간접 피드백: 매 T iter 재할당.
- **핵심: 메커니즘 1과 동시 작용.** 매 iter에서 n_i에 L_mutual + L_normal_align gradient 동시 합산.
  메커니즘 2의 기하 정렬 → 메커니즘 1이 정렬된 n_i로 f_i 교정 → 다음 그룹 재할당에 반영.
  이 동시 작용 + 주기적 재할당의 순환이 순차 파이프라인과의 차별점.
- s_i 별도 제약 없음: Stage 3 폴리곤 경계가 대표 평면 교차로 결정되어 s_i에 미의존.

## Semantic Class (K=4)
| Index | Class | CityGML | 역할 |
|-------|-------|---------|------|
| 0 | BG | — | ignore_index |
| 1 | Roof | RoofSurface | 직접 매핑 |
| 2 | Wall | WallSurface | 직접 매핑 |
| 3 | Terrain | — | Context + gravity + 지면 높이 |

## Gravity
Grounded SAM terrain MVS 법선 평균. 학습 전 1회 계산.

## 연구 계획 구조
- **Phase 1** — MatrixCity(벤치마크)에서 Stage 2 각 단계가 레퍼런스(CityGSV2, ULSR-GS) 수준 달성 확인
- **Phase 2** — 3D BAG 합성 렌더링에서 Stage 2+3 end-to-end + 4조건 ablation(CityGML 품질)
- **Phase 3** — GauU-Scene(real UAV) + 순차 파이프라인 비교 + 성수동 실데이터 시연

## 데이터셋 용도
- Stage 2 검증: MatrixCity Small City Aerial (메인), GauU-Scene (서브)
- Stage 3 검증: 3D BAG 합성 렌더링 (GT CityGML 있음)
- 실데이터 시연: 성수동 (Metashape depth 사용)

## Ablation 4조건
Baseline / Mutual only / Structure only / Both — 메커니즘 1/2 개별 기여 분리

## 현재 진행 상태
- [x] Stage 1 완료 (성수동)
- [x] PlanarSplatting 예비 실험 완료 (legacy/)
- [x] Synthetic A 완료 (results/synthetic_a/)
- [x] gsplat 환경 구축 + gradient_2dgs 버그 수정
- [x] Phase 1 완료 (MatrixCity, 6/6 통과, PSNR 22.26)
- [x] Phase 2-1 완료 (3D BAG 합성 파이프라인, Amsterdam Jordaan 131건물)
- [x] Phase 2-2 Stage 2 완료 (4조건 30k 학습, G1 grouping)
- [x] Phase 2-2 Stage 3 완료 (convex polytope, post-bbox-fix)
- [x] C3 진단 완료 — photo loss redundancy 확정 (gradient L_mutual의 1/135)
- [x] Cycle 검증 완료 — G1 위에서 4고리 모두 약함 입증
- [x] Track 1 (인터페이스 정렬) 시도 — **patch vs surface unit mismatch로 실패**
- **발견 사항:**
  - C1: Mutual val3dity 회귀 -3.8%p (bbox fix 전 -8.4%p)
  - C2: Stage 2 group(G1, patch 단위 154개)과 Stage 3 surface(6-9개)가 다른 단위
  - C3: 3 component — C3a photo redundancy 확정, C3b patch unit, C3c cycle 부재
  - G1(voxel hash 5cm + 12 dir bin)이 thesis 의도(surface 단위)와 불일치
  - GT_convex reference 오류 (절반 높이 축소) — 진짜 천장 미정
  - Building 1 직접 검증: 우리 출력 16.41m ≈ GT 16.61m (알고리즘 작동)
- [ ] **G2 (surface-level grouping) 설계 + 구현** ← **현재 블로커**
- [ ] Phase 2 재학습 (Structure/Both with G2)
- [ ] 4조건 Stage 3 재측정 (G2 기반)
- [ ] Cycle 재검증 (G2 위에서)
- [ ] GT 천장 재측정
- [ ] Phase 3: GauU-Scene + 순차 비교 + 성수동

## 현재 병목
**G2 (surface-level grouping).** G1(voxel hash 5cm)은 patch 단위로, thesis가 의도한 "평면 인스턴스 그룹"(surface 단위)과 불일치. L_normal_align이 intra-patch smoothing에 그쳐 차별화 안 됨. Cycle 4고리 모두 약함 입증.

G2로 전환 시: thesis-구현 일치, Stage 2-3 인터페이스 자연 통합, cycle 의미 있음.
Structure/Both만 재학습 필요. Baseline/Mutual은 post-hoc G2.
C3a(photo redundancy)는 G2로도 해소 안 됨 — Phase 3에서 검증.

**Measurement fragility 주의:** bbox 1줄 + GT_convex 두 차례 측정 오류. 모든 재측정에 GT sanity check 필수.

## 중요 규칙
- **gsplat 라이브러리** 사용 (2DGS 공식 fork 아님)
- **미분 가능 렌더링** 용어 통일 (뉴럴 렌더링 X)
- **Intra/inter** 표현: 메커니즘 1=intra, 메커니즘 2=inter
- **Gravity**: terrain MVS 법선 사전 추정. hardcoded 금지.
- **법선**: "벽의 법선은 수평(gravity에 수직)"
- **L_nc**: 독립 손실 (L_geo로 묶지 않음)
- **L_coverage**: 후보
- 각 Step 완료 시 results/에 REPORT.md 생성
- 시각적 산출물 필수