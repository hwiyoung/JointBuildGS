# JointBuildGS research documents

`docs/`에는 사람이 읽거나 검토하는 정본만 둔다. 직접 파일은 이 안내서 하나뿐이며,
파일 확장자가 아니라 역할로 네 영역을 구분한다.

| 영역 | 소유하는 내용 | 대표 진입점 |
|---|---|---|
| `research/` | 연구 맥락, 방법론, 사전등록, 결정, 재현성, 저장소 지도 | [`research/README.md`](research/README.md) |
| `experiments/` | 연구 목적별 보고서, 표, 지표, compact manifest | [`experiments/README.md`](experiments/README.md) |
| `evidence/` | 동결 검토 패키지와 superseded 자료의 보존 archive | [`evidence/README.md`](evidence/README.md) |
| `figs/` | 보고서가 참조하는 선별 그림 | `figs/<experiment-family>/` |

## 시작점

- 연구 맥락: [`research/RESEARCH_CONTEXT.md`](research/RESEARCH_CONTEXT.md)
- 실험 계획: [`research/EXPERIMENT_PLAN.md`](research/EXPERIMENT_PLAN.md)
- 저장소 계약: [`research/repository/TOP_LEVEL_DIRECTORY_CONTRACT.md`](research/repository/TOP_LEVEL_DIRECTORY_CONTRACT.md)
- 현재 구조: [`research/repository/REPOSITORY_STRUCTURE_FINAL.md`](research/repository/REPOSITORY_STRUCTURE_FINAL.md)
- 문서 정본 지도: [`research/repository/CANONICAL_MAP.md`](research/repository/CANONICAL_MAP.md)
- 과거 문서 archive: [`evidence/archive/README.md`](evidence/archive/README.md)
- storage 감사와 정책: [`research/REPO_STORAGE_AUDIT.md`](research/REPO_STORAGE_AUDIT.md),
  [`research/PROPOSED_STORAGE_POLICY.md`](research/PROPOSED_STORAGE_POLICY.md)

## Experiment layout

새 결과는 `experiments/<research-purpose>/<experiment-family>/` 아래에 놓는다. 그 안에서
`reports/`, `tables/`, `metrics/`, `manifests/`, `models/`를 산출물 역할에 따라 사용한다.
Raw logs, checkpoint, point cloud, mesh, 전체 image/render bundle은 `docs/`에 두지 않는다.

## 자동 인벤토리

다음 파일은 `scripts/repository/repo_inventory.py`와
`configs/repository/repo_inventory.json`으로 생성한다.

- [`research/repository/DOCUMENT_CATALOG.csv`](research/repository/DOCUMENT_CATALOG.csv)
- [`research/repository/DOCUMENT_LINEAGE.csv`](research/repository/DOCUMENT_LINEAGE.csv)
- [`research/repository/CANONICAL_MAP.md`](research/repository/CANONICAL_MAP.md)
- [`research/repository/CATALOG_ISSUES.md`](research/repository/CATALOG_ISSUES.md)
- [`../phases/RUN_CATALOG.csv`](../phases/RUN_CATALOG.csv)

```bash
docker compose run --rm dev \
  python scripts/repository/repo_inventory.py \
  --config configs/repository/repo_inventory.json
```

생성된 candidate 표시는 과학적 판정이 아니다. Frozen manifest와 run receipt의 과거 경로는
그 당시 provenance로 유지하고, `research/repository/migrations/`와 artifact manifest가 현재
위치를 해석한다.
