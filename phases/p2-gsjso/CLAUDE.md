# P2 — GS-JSO 코어 실행 가이드 (Claude Code용)

> 레포 인덱스·§4 불변 규칙: 루트 `CLAUDE.md` / `AGENTS.md`. 사람 검토자: 김휘영.
> 이 문서의 모든 상대 경로는 레포 루트 기준(GS-JSO 코어 코드는 루트 `src/`·`configs/`).
> P2 단계 산출(스크립트·환경)은 `phases/p2-gsjso/` 기준.

> ⚠️ **DRAFT 골격 (확인 요망):** 아래 **P2-spike 태스크**·**5-way 비교**·**성공기준**은
> 착수 메시지에 명시되지 않아 프로젝트 맥락(루트 GS-JSO 문서의 손실/메커니즘/Ablation 4조건,
> P0 `표기` 라인의 "P2 GS-JSO 코어 A1: semantic+geom-sem", "E5 미니·MVS 대비 correction gain")에서
> 추정해 작성했다. **정확한 spike 스코프·5-way 정의·임계값은 사람이 확정**한다. 에이전트는
> 수치 산출까지만(P0와 동일 규약).

## 1. 목적 (한 줄)

P0가 보인 점군 중간표현의 약점(무텍스처·노이즈 → 구조화 실패·품질 저하)을, 미분 가능 렌더링
기반 평면 프리미티브(2DGS, **gsplat**) 위에서 **기하–의미론을 공동 최적화**(intra `L_mutual` +
inter `L_structure`)하여 우회한다. P2-spike는 이 공동 최적화 기계장치가 **실제로 surface
evidence를 개선하는지**를 작은 장면에서 최소 비용으로 검증한다(go/no-go).

## 2. GS-JSO 맥락 요약 (상세: 루트 `docs/RESEARCH_CONTEXT.md`·`docs/EXPERIMENT_PLAN.md`)

**손실**
```
L = L_depth + L_normal + λ_nc·L_nc + λ_s·L_sem + λ_p·L_photo + λ_m·L_mutual + λ_str·L_structure
```
- `L_depth`→c_i (MVS depth L1), `L_normal`→n_i (MVS normal cosine), `L_nc`→n_i,c_i (독립 손실),
  `L_sem`→f_i (CE, ignore_index=0), `L_photo`→all (L1+SSIM).

**메커니즘 1 (intra, `L_mutual`)** — n_i·f_i 양방향, c_i는 L_height 높이만, s_i 없음.
- `L_vert`(벽 법선→수평), `L_slope`(roof 수평이면 penalty), `L_horiz`(terrain 법선→수직),
  `L_height`(roof>terrain). 핵심: p_c × 기하오차 곱 → 양방향 gradient(f_i ↔ n_i).

**메커니즘 2 (inter, `L_structure`)** — 매 T iter 그룹핑(동일 class + 법선 유사 + 공간 근접).
- `L_normal_align`(그룹 법선→대표, n_k detach), `L_coplanar`(중심→대표 평면, n_k/d_k detach),
  `L_coverage`(후보). f_i 직접 gradient 없음(그룹 할당=argmax 이산). 메커니즘 1과 동시 작용.

**프리미티브 G_i**: c_i(N,3) 중심 · n_i=t_u×t_v 법선 · s_i(N,2) in-plane scale ·
f_i(N,4) 의미론(BG/Roof/Wall/Terrain) · color_i(SH).
**Semantic K=4**: 0 BG(ignore) / 1 Roof→RoofSurface / 2 Wall→WallSurface / 3 Terrain(context+gravity).
**Gravity**: terrain MVS 법선 평균, 학습 전 1회 (hardcoded 금지).

## 3. P2-spike 태스크 (DRAFT)

> 목표: gsplat+2DGS 기반에 `L_mutual`·`L_structure` 훅을 최소 구현하고, 한 작은 장면에서
> 짧은 학습 예산으로 **5-way**를 돌려 "공동 최적화가 surface evidence를 개선하는가"를 본다.
> 판정은 사람. 산출은 수치·시각화까지.

- **베이스**: Phase 1 완료분(MatrixCity Aerial, 6/6 통과, PSNR 22.26)을 출발점으로.
  GS-JSO 코어는 루트 `src/`·`configs/` 그대로 사용(이동 금지).
- **데이터**: Stage 2 검증 메인 = MatrixCity Small City Aerial(서브셋 1장면). gravity는 terrain
  MVS 법선으로 사전 추정.
- **구현 범위(spike 최소셋)**:
  1. 메커니즘 1 `L_mutual` 4항(L_vert/L_slope/L_horiz/L_height) 최소 구현 + n_i·f_i 양방향 확인.
  2. 메커니즘 2 `L_structure`(L_normal_align·L_coplanar) 매 T iter 그룹핑 훅.
  3. 5-way를 동일 seed·동일 예산으로 학습.
- **계측**: 렌더 normal–depth normal consistency, 벽 법선 수평오차, roof/terrain 높이 순서,
  semantic mIoU, PSNR(품질 회귀 확인), 그리고 **MVS 대비 correction gain**(P0가 약점 보인
  무텍스처·노이즈 영역에서 GS-JSO surface evidence가 MVS를 회복/상회하는지).
- **산출**: `phases/p2-gsjso/`에 번호 순 스크립트, `results/`에 REPORT.md + 시각 산출(필수),
  5-way 비교표 + per-condition 시각화.

## 4. 5-way 비교 (DRAFT — 1 MVS 기준선 + 4 Ablation)

| # | 조건 | L_mutual | L_structure | 역할 |
|---|------|:---:|:---:|------|
| 1 | **MVS baseline** | — | — | 비-GS 기준선. P0 DIM/MVS surface(=비교 하한). correction gain 측정 대상 |
| 2 | **Baseline (2DGS)** | ✗ | ✗ | 공동 최적화 없는 gsplat+2DGS |
| 3 | **Mutual only** (메커니즘 1) | ✓ | ✗ | intra-primitive 도메인 교정 단독 기여 |
| 4 | **Structure only** (메커니즘 2) | ✗ | ✓ | inter-primitive 구조 정렬 단독 기여 |
| 5 | **Both** (1+2) | ✓ | ✓ | 결합 효과 (목표 구성) |

- 2–5는 루트 GS-JSO 문서의 **Ablation 4조건**(Baseline/Mutual/Structure/Both) 그대로.
- 1(MVS)을 더해 **"GS-JSO Both vs MVS"** correction gain을 직접 비교(E5 동기와 일치).
- G1 cycle 정정 반영: 메커니즘 1·2는 순환이 아니라 **독립 효과 + 결합 효과**로 평가(3·4·5 대비).

## 5. 성공기준 메모 (DRAFT — 임계값은 사람 확정)

go/no-go 게이트 후보 (P0 판정 스타일: 에이전트는 수치, 판정은 사람):

- **G-A 수렴/무회귀**: 5-way 학습 안정, Both PSNR이 Baseline 대비 의미 있는 회귀 없음.
- **G-B 메커니즘 효과**: Both가 Baseline 대비 타깃 지표 개선 — 벽 법선 수평오차 ↓,
  roof/terrain 높이 순서 정합 ↑, normal–depth consistency ↑.
- **G-C 분리 기여**: Mutual-only(3)·Structure-only(4) 각각 자기 타깃 지표에서 Baseline(2) 상회
  (각 메커니즘이 독립적으로 기여).
- **G-D correction gain**: Both(5)의 surface evidence가 P0 약점 영역(무텍스처·노이즈)에서
  MVS(1)를 회복/상회 — P2의 핵심 가설.
- **임계값 TODO(사람)**: 각 지표의 합·불 경계(예: 법선오차 Δ, mIoU Δ, gain %)는 spike 1차
  결과 분포를 보고 확정. P0처럼 "2개 이상 충족" 식 게이트로 정형화 검토.

## 6. 불변 규칙

루트 `CLAUDE.md` §4(repo-wide)를 따른다. P2 핵심:
- **Docker 기반**(호스트 직접 설치 금지) · **gsplat 라이브러리**(2DGS 공식 fork 아님) ·
  "**미분 가능 렌더링**" 용어 · **Gravity는 사전 추정**(hardcoded 금지).
- **한 태스크 = 한 커밋**(태스크 ID) · run마다 버전·커밋·파라미터 기록 · 실패는 숨기지 말고 기록.
- **GT 사용 분리**(루트 §4-9) · 각 실험 완료 시 `results/`에 REPORT.md + 시각 산출 필수.
