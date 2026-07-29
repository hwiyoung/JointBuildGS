# P2 — GS-JSO 코어 (Geometry–Semantics Joint Optimization)

> 단계 상태: 🚧 진행 (P2-spike 착수). 레포 인덱스: 루트 `CLAUDE.md` / `AGENTS.md`.
> 이 단계의 작업 가이드·태스크·성공기준: [`CLAUDE.md`](CLAUDE.md).

## 목적

P0(`phases/p0-audit/`)는 점군 중간표현(특히 영상 유래 DIM)이 무텍스처·노이즈 영역에서
구조화 실패·품질 저하를 일으킴을 보였다. **P2는 그 약점을 미분 가능 렌더링 기반 평면
프리미티브(2DGS, gsplat)에서 기하–의미론을 공동 최적화**하여 우회한다.

- **메커니즘 1 (intra, `L_mutual`)**: 개별 프리미티브의 도메인 규칙 기반 상호 교정.
- **메커니즘 2 (inter, `L_structure`)**: 프리미티브 간 구조적 일관성 제약.

## 구조와 소유권

```
phases/p2-gsjso/
  CLAUDE.md, AGENTS.md  # P2 규칙과 성공기준
  docs/                 # phase 운영·issue 문서
  configs/              # run/lock에 고정된 phase config
  scripts/              # SHA·경로·Git ref로 잠긴 구현과 phase 전용 helper
  runs/                 # compact receipts 및 기존 실행 기록
```

재사용 가능한 실험 드라이버는 `scripts/experiments/<family>/`, 대응 테스트는
`tests/experiments/<family>/`가 정본이다. P2 reusable-code wave 1에서 degradation curve,
E5 C001 S3B0, pilot one-wave를 이 구조로 승격했다. 정확한 매핑은
`docs/catalog/migrations/P2_SCRIPT_PATHS_WAVE1.csv`에 있다.

## GS-JSO 코어 코드 (레포 루트)

P2 구현은 레포 루트의 기존 GS-JSO 코드를 사용/확장한다. **이동하지 않고 참조**한다:

- `src/` — 모델·손실·grouping·train
- `configs/` — 실험 config
- `scripts/`, `tools/` — 재사용 드라이버와 레포 도구
- `results/` — 실험 산출(REPORT.md 등)
- 연구 맥락: `docs/research/RESEARCH_CONTEXT.md`(손실·파라미터), `docs/research/EXPERIMENT_PLAN.md`(실험 순서)

> 현재 ignore 규칙과 기존 실행 데이터는 이번 구조 정리에서 변경하지 않았다. 새로운 저장
> 정책이나 외부 artifact backend는 별도 승인 작업으로만 도입한다.
