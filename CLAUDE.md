# 도시 규모 건물의 구조적 3D 복원을 위한 기하-의미론 공동 최적화

## 프로젝트 개요
미분 가능 렌더링 기반 평면 프리미티브(2DGS) 위에 건물 도메인 지식과 면 단위 구조 인식을 통합하여, 건물의 재구성과 구조화를 공동 최적화하는 박사 연구. Stage 2의 joint-optimized evidence를 Roofer-style evidence-to-CityGML read-out으로 변환하여 CityGML LOD2 semantic shell을 생성한다.

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
- **Stage 3**: Evidence-to-CityGML read-out (Roofer-style 2.5D roof-partition, 외부 roofprint 미사용)

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
- **메커니즘 1과 동시 작용.** 매 iter에서 n_i에 L_mutual + L_normal_align gradient 동시 합산.

**G1 cycle effect 정정:** P1-3b cycle 검증에서 G1 cycle 4고리는 거의 정적이었음. "메커니즘 1과 2의 순환 효과"보다는 **두 메커니즘의 독립 효과 + 결합 효과**로 평가. cycle of feedback이 아니라 surface evidence quality 개선이 핵심.

## Semantic Class (K=4)
| Index | Class | CityGML | 역할 |
|-------|-------|---------|------|
| 0 | BG | — | ignore_index |
| 1 | Roof | RoofSurface | 직접 매핑 |
| 2 | Wall | WallSurface | 직접 매핑 |
| 3 | Terrain | — | Context + gravity + 지면 높이 |

## Gravity
Grounded SAM terrain MVS 법선 평균. 학습 전 1회 계산.

## 현재 병목 — Stage 3 Evidence-to-CityGML read-out

최신 실험 결과, Stage 3의 병목은 더 이상 단순한 primitive normal clustering 또는 렌더링 기반 surface 추출 문제가 아니다. v4-mode는 Mutual 조건에서 wall over-merge를 상당히 완화했으며 (P1-2 Mutual 4/5 GO), PolyFit/convex polytope 실험은 local surface candidate를 generic plane assembly로 바로 조립하면 valid-small solid, non-manifold error, coverage collapse가 발생함을 정량적으로 보였다.

**Stage 3 재정의:**
Stage 3 = Stage 2에서 생성된 wall / roof / terrain evidence를 CityGML LOD2 semantic shell로 변환하는 evidence-to-CityGML read-out.

구체적으로 Stage 3는 Roofer-style 2.5D roof-partition read-out을 따른다. 기존 Roofer/3DBAG는 point cloud와 외부 roofprint polygon을 입력으로 사용하지만, 본 연구는 외부 roofprint를 사용하지 않고 Stage 2의 joint-optimized evidence에서 building instance, footprint/roofprint, roof partition을 추정한다.

처리 순서:
1. building evidence partition
2. wall-derived footprint / roofprint estimation
3. roof evidence projection and roof partition
4. roof-wall-ground semantic surface assembly
5. CityJSON / CityGML export
6. val3dity + height + coverage + precision 평가

P1-4a Part B에서 6건 GT-derived per-building relation read-out이 read-out feasibility를 보였다 (simple/medium 4건 coverage 90-100%, h_err 0.00m). 전체 scene에서 building instance를 자동으로 나누는 문제는 별도 Stage 3-0(automatic split)으로 검증한다.

## 데이터셋 용도
- Stage 2 검증: MatrixCity Small City Aerial (메인), GauU-Scene (서브)
- Stage 3 검증: 3D BAG 합성 렌더링 Amsterdam Jordaan 131건물 (GT CityGML 있음)
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
- [x] Stage 3 backend 비교 audit (v4 mode-based clustering, convex polytope, PolyFit, 2.5D, RANSAC)
  - v4 mode-based clustering: Mutual 4/5 GO (P1-2)
  - convex polytope: P1-3b 4 condition ablation, height/coverage collapse → NG
  - PolyFit (CGAL+SCIP+repair recipe): GT input 40% val3dity, simple flat만 정확 재구성, hip/complex valid-small 또는 over-segment → 본 thesis Stage 3로 부적합
  - 2.5D extrusion: val3dity 67.2%, quality 미측정 (별도 알고리즘으로 분리)
  - RANSAC: 2/5 spot-check
- [x] **P1-4a Part B 완료 — Roofer-style relation read-out feasibility 확인**
  - simple/medium 4건 (B1 flat, B2 flat, B8 gable, B0 tri-slope): coverage 90-100%, h_err 0.00m
  - hip 1건 (B6): coverage 88.3%, h_err 3.61m
  - complex 1건 (B3): coverage 36.5%, h_err 7.31m
  - val3dity NOT_RUN (validator missing) → E0 preflight에서 formal pass/fail 확인 필요
- [ ] **E0: val3dity preflight + precision metric 재실행** ← **즉시 시작**
- [ ] E1: GT-derived 131 per-building relation read-out
- [ ] E2: GT-derived full-scene automatic building split
- [ ] E3: Stage2-derived primitives + GT oracle split (4조건)
- [ ] E4: Stage2-derived full-scene automatic split + read-out (4조건, end-to-end)
- [ ] Phase 3: GauU-Scene + 성수동

## 현재 우선순위
**E0 → E1 → E2/E3 병렬 → E4** 순서.
- E0/E1: 1주 내
- E2/E3: 2주
- E4: E1-E3 결과에 따라 진행

## 중요 규칙
- **gsplat 라이브러리** 사용 (2DGS 공식 fork 아님)
- **미분 가능 렌더링** 용어 통일 (뉴럴 렌더링 X)
- **Intra/inter** 표현: 메커니즘 1=intra, 메커니즘 2=inter
- **Gravity**: terrain MVS 법선 사전 추정. hardcoded 금지.
- **법선**: "벽의 법선은 수평(gravity에 수직)"
- **L_nc**: 독립 손실 (L_geo로 묶지 않음)
- **L_coverage**: 후보
- **Stage 3**: Roofer-style evidence-to-CityGML read-out. 외부 roofprint 미사용.
- **GT 사용 분리**:
  - GT building id: per-building sanity (E1, E3 oracle split) — read-out 입력 가능
  - GT footprint / roof type / final roof model: read-out 입력 절대 금지, evaluation only
  - 최종 end-to-end (E4): GT 일체 미사용, evaluation only
- 각 실험 완료 시 results/에 REPORT.md 생성
- 시각적 산출물 필수
## P0 입력 치환 Audit
P0 작업은 p0-audit/에서 수행하며 p0-audit/CLAUDE.md를 따른다. GS-JSO 구현 규칙과 독립.
