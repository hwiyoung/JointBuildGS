# P2 — GS-JSO 코어 (Geometry–Semantics Joint Optimization)

> 단계 상태: 🚧 진행 (P2-spike 착수). 레포 인덱스: 루트 `CLAUDE.md` / `AGENTS.md`.
> 이 단계의 작업 가이드·태스크·성공기준: [`CLAUDE.md`](CLAUDE.md).

## 목적

P0(`phases/p0-audit/`)는 점군 중간표현(특히 영상 유래 DIM)이 무텍스처·노이즈 영역에서
구조화 실패·품질 저하를 일으킴을 보였다. **P2는 그 약점을 미분 가능 렌더링 기반 평면
프리미티브(2DGS, gsplat)에서 기하–의미론을 공동 최적화**하여 우회한다.

- **메커니즘 1 (intra, `L_mutual`)**: 개별 프리미티브의 도메인 규칙 기반 상호 교정.
- **메커니즘 2 (inter, `L_structure`)**: 프리미티브 간 구조적 일관성 제약.

## 구조 (골격)

```
phases/p2-gsjso/
  CLAUDE.md     # P2-spike 태스크 + 5-way 비교 + 성공기준 (작업 가이드)
  README.md     # 이 파일 (오리엔테이션)
  scripts/      # 번호 순 실행 스크립트 (01_, 02_, ...) — 골격
  env/          # Docker 환경 (Dockerfile/compose/versions.md) — 골격
```

## GS-JSO 코어 코드 (레포 루트, 이동 금지 · 참조만)

P2 구현은 레포 루트의 기존 GS-JSO 코드를 사용/확장한다. **이동하지 않고 참조**한다:

- `src/` — 모델·손실·grouping·train
- `configs/` — 실험 config
- `scripts/`, `tools/` — 루트 GS-JSO 스크립트·도구
- `results/` — 실험 산출(REPORT.md 등)
- 연구 맥락: `docs/RESEARCH_CONTEXT.md`(손실·파라미터), `docs/EXPERIMENT_PLAN.md`(실험 순서)

> 로컬 데이터·런 산출은 gitignore된다. P2 데이터/런 디렉토리는 추가 시 루트 `.gitignore`에
> `phases/p2-gsjso/data/`·`phases/p2-gsjso/runs/` 패턴으로 등록한다(P0와 동일 규약).
