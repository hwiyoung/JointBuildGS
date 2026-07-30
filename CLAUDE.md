# JointBuildGS — 레포 인덱스 (Claude Code용)

> 다른 에이전트(Codex 등)는 AGENTS.md(동일 내용)를 읽는다. 사람 검토자: 김휘영.
> 이 파일은 **슬림 인덱스**다. 단계별 상세 가이드·태스크·규칙은 해당 phase 디렉토리의
> `CLAUDE.md`/`AGENTS.md`를 읽는다.

## 레포 개요

**도시 규모 건물의 구조적 3D 복원을 위한 기하–의미론 공동 최적화** (박사 연구).
미분 가능 렌더링 기반 평면 프리미티브(2DGS, **gsplat**) 위에 건물 도메인 지식과 면 단위
구조 인식을 통합하여 건물의 재구성과 구조화를 **공동 최적화**(intra-primitive `L_mutual` +
inter-primitive `L_structure`)하고, Stage 2의 joint-optimized evidence를 Roofer-style
evidence-to-CityGML read-out으로 변환해 CityGML LOD2 semantic shell을 생성한다.

- 파이프라인: **Stage 1** SfM/MVS + 2D Seg + Gravity → **Stage 2** 구조 인식 공동 최적화 →
  **Stage 3** Evidence-to-CityGML read-out (외부 roofprint 미사용).
- 깊은 연구 맥락(손실 함수·메커니즘 1/2·프리미티브·파라미터): `docs/research/RESEARCH_CONTEXT.md`,
  `docs/research/EXPERIMENT_PLAN.md`.

## 단계 색인 (phases/)

| 단계 | 상태 | 위치 | 가이드 |
|------|------|------|--------|
| **P0** 입력치환 Audit | ✅ 완료 | `phases/p0-audit/` | `phases/p0-audit/CLAUDE.md` · `AGENTS.md` |
| **P2** GS-JSO 코어 | 🚧 진행 | `phases/p2-gsjso/` | `phases/p2-gsjso/CLAUDE.md` |

- **P0 완료 → `phases/p0-audit/`** — ALS(Ref-L) vs 영상 유래 DIM(Seq-G) 입력 치환 audit
  (W1 입력준비·진단 → W2 audit → W3 지표·통합 → W4 G1 보고). 핵심: DIM 재구성 실패 8건 vs
  ALS 0건(McNemar p=0.0078), 점군 중간표현의 약점이 GS-JSO의 동기. G1 판정 대기.
- **P2 진행 → `phases/p2-gsjso/`** — gsplat+2DGS 위 `L_mutual`·`L_structure` 공동 최적화 spike.
- **GS-JSO 코어 구현 코드는 레포 루트에 그대로 둔다** (이동 금지, phase 문서는 참조만):
  `src/`, `configs/`, `scripts/`, `tools/`, `tests/`, `docs/`, `phases/`, `artifacts/`,
  `external/`, `legacy/`,
  `Dockerfile`, `docker-compose.yml`, `requirements.txt`.
- 대용량 runtime payload는 sibling `../JointBuildGS-artifacts`에 있고, Docker가 과거
  `data/`·`results/` 경로를 compatibility mount한다. Git 정본 결과는 `docs/experiments/`,
  resolver는 `artifacts/manifests/`가 소유한다.

## §4 불변 규칙 (repo-wide)

> P0 §4(9개 불변 규칙)와 GS-JSO 중요 규칙을 통합한 레포 전역 규칙. 단계별 전체 규칙은
> 각 phase 문서를 따른다 — P0 전체 9개 규칙: `phases/p0-audit/CLAUDE.md` §4.

1. **Docker 기반 개발** — 모든 도구 실행은 컨테이너로. 호스트(conda 등) 직접 설치 금지.
2. **재현성** — 손 실행 금지. 모든 처리는 `scripts/` + config로 재현 가능해야 하며,
   도구 버전·커밋·파라미터를 run마다 기록한다.
3. **한 태스크 = 한 git 커밋** — 커밋 메시지에 태스크 ID.
4. **실패·예외는 숨기지 말고 기록 후 보고** (해당 phase의 `issues` 로그).
5. **지오 산출물 CRS = EPSG:25832 통일** (P0·공간 데이터). 모든 점군/벡터 산출물에 CRS 명시.
6. **gsplat 라이브러리 사용** (2DGS 공식 fork 아님). "**미분 가능 렌더링**" 용어 통일(뉴럴 렌더링 X).
7. **Gravity는 terrain MVS 법선 사전 추정** — hardcoded 금지. "벽의 법선은 수평(gravity에 수직)".
8. **Stage 3는 Roofer-style evidence-to-CityGML read-out** — 외부 roofprint 미사용.
9. **GT 사용 분리** — building id는 per-building sanity(E1·E3 oracle split) 입력 가능;
   footprint·roof type·final roof model은 **evaluation only(입력 금지)**; 최종 end-to-end(E4)는 GT 일체 미사용.
   - **(iii) 1파 범위 예외** — 승인 잠금판
     `docs/research/preregistration/quality_axis/사전등록서_품질축본선_승인잠금v4_20260721.md`에만 LoD2
     `GroundSurface` **XY**를 기존 C001/E5와 동일한 공통 표준 footprint로 허용한다.
     이 출처를 non-GT로 재분류하지 않고 manifest에 기록하며, honest arm에 LoD2 Z·
     `RoofSurface`·roof type·semantic class·final roof model을 입력하지 않는다. E4 금지는 유지한다.
