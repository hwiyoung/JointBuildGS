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

재사용 가능한 실행기는 기능별 `scripts/<scientific-role>/`, 대응 검증은
`tests/<workstream>/`가 정본이다. P2 reusable-code wave 1에서 degradation curve,
E5 C001 S3B0, pilot one-wave를 이 구조로 승격했다. 정확한 역사적 매핑은
`docs/research/repository/migrations/P2_SCRIPT_PATHS_WAVE1.csv`에 있다.

`phases/`는 범용 코드의 중복 보관소가 아니다. 아직 종료되지 않은 단계의 잠금 config,
단계에만 종속된 절차, compact run receipt를 보존한다. 단계가 종료되면 재사용 코드는
`src/`·`scripts/`·`configs/`로 승격하고, 검토 패키지는 `docs/evidence/`로 동결한다.

## GS-JSO 코어 코드 (레포 루트)

P2 구현은 레포 루트의 기존 GS-JSO 코드를 사용/확장한다. **이동하지 않고 참조**한다:

- `src/` — 모델·손실·grouping·train
- `configs/` — 실험 config
- `scripts/` — 재사용 드라이버와 저장소 점검 도구
- `docs/experiments/<family>/{reports,tables,metrics,manifests,models}/` — 역할별로 승격된 compact result evidence
- `artifacts/manifests/` — 외부 dataset/checkpoint/render/run payload resolver
- 연구 맥락: `docs/research/RESEARCH_CONTEXT.md`(손실·파라미터), `docs/research/EXPERIMENT_PLAN.md`(실험 순서)

> 2026-07-30에 P0 및 과거 result payload는 sibling artifact backend로 물리 이전했다.
> 활성 Fusion-W1의 non-index payload도 manifest로 외부화했으며, phase에는 사용자가 편집 중인
> control/receipt 경계만 남겼다. run closeout 뒤 동일 manifest 절차로 동결한다.
