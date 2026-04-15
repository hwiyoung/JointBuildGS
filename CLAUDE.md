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
| t_u, t_v | (N,3)×2 | tangent 벡터 (학습 파라미터) |
| n_i | (N,3), derived | 법선 = normalize(t_u × t_v) |
| s_i | (N,2) | in-plane scale |
| opacity_i | (N,1) | 불투명도 |
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
- 핵심: p_c × 기하 오차의 곱 → 양방향 gradient
- 안전장치: L_sem이 f_i를 GT 방향으로 강제하여 p_c→0 trivial solution 방지

## 메커니즘 2: Inter-primitive (L_structure)
- 매 T iter 그룹핑: 동일 class + 법선 유사 + 공간 근접
- L_normal_align: 같은 그룹 법선 → 대표 법선 (n_k detach)
- L_coplanar: 같은 그룹 중심 → 대표 평면 위 (n_k/d_k detach)
- L_coverage: 후보 (densification 대비 검증)

## Semantic Class (K=4)
| Index | Class | CityGML | 역할 |
|-------|-------|---------|------|
| 0 | BG | — | ignore_index |
| 1 | Roof | RoofSurface | 직접 매핑 |
| 2 | Wall | WallSurface | 직접 매핑 |
| 3 | Terrain | — | Context + gravity + 지면 높이 |

## Gravity
Grounded SAM terrain MVS 법선 평균. 학습 전 1회 계산.

## 현재 진행 상태
- [x] Stage 1 완료
- [x] PlanarSplatting 예비 실험 완료 (legacy/)
- [x] Synthetic A 완료 (results/synthetic_a/)
- [x] Phase 1 Step 1-0: 리포지터리 셋업 + 마이그레이션 (results/phase1_setup/REPORT.md)
- [ ] **Phase 1 Step 1-1**: gsplat/2DGS vanilla 학습 ← **현재**
- [ ] Phase 1 Step 1-2: Semantic head + L_sem
- [ ] Phase 1 Step 1-3: L_mutual 이식
- [ ] Phase 1 Step 1-4: 통합 검증
- [ ] Phase 2: Ablation (Baseline/Joint/Joint+Structure)
- [ ] Phase 3: Stage 3 + 비교

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
