# JointBuildGS

도시 규모 건물의 구조적 3D 복원을 위한 기하-의미론 공동 최적화 연구 저장소다. 연구 개요와 불변 규칙은 [`AGENTS.md`](AGENTS.md), 상세 연구 맥락은 [`docs/README.md`](docs/README.md)에서 시작한다.

## 폴더 지도

| 경로 | 유일한 책임 | 기본 storage 등급 |
|---|---|---|
| `src/` | 여러 실험에서 import하는 재사용 구현 | A. regular Git |
| `configs/` | 코드와 분리된 버전 관리 파라미터 | A |
| `scripts/` | config와 `src/`를 연결하는 재현 가능한 실행 진입점 | A |
| `tools/` | catalog, 검사, 변환 등 저장소 유지보수 도구 | A |
| `tests/` | 코드·실행 계약·lineage의 자동 검증 | A |
| `docs/` | 사람이 읽는 정본 연구 지식과 승격된 compact evidence | A, 일부 향후 B |
| `phases/` | 단계별 규칙, issue ledger, compact run/provenance receipt | A |
| `artifacts/` | 향후 외부 artifact를 가리키는 작은 manifest만 저장 | C manifest는 A |

`docs/`와 `phases/`는 중복 폴더가 아니다. 결과 해석·보고서·승인된 표와 그림은 `docs/`가 소유하고, 그 결과가 어떤 규칙·commit·config·container·run에서 나왔는지는 `phases/`가 소유한다. 대용량 checkpoint, dataset, point cloud, mesh, 전체 image bundle은 외부 저장소와 manifest가 담당해야 한다.

```text
configs/ + scripts/ + src/
             |
             v
phases/<phase>/runs/<run_id>/receipt
             |                         \
             | promotes                 \ resolves
             v                           v
docs/experiments/<family>/          artifacts/manifests/<id>
report + compact evidence               -> external storage
```

전체 계약과 현재 예외는 [`docs/catalog/TOP_LEVEL_DIRECTORY_CONTRACT.md`](docs/catalog/TOP_LEVEL_DIRECTORY_CONTRACT.md), 실제 정리 결과는 [`docs/catalog/REPOSITORY_STRUCTURE_FINAL.md`](docs/catalog/REPOSITORY_STRUCTURE_FINAL.md)에 있다.

## 문서와 phase 진입점

- 연구 문서: [`docs/README.md`](docs/README.md)
- phase 및 run: [`phases/README.md`](phases/README.md)
- 자동 문서 catalog: [`docs/catalog/CANONICAL_MAP.md`](docs/catalog/CANONICAL_MAP.md)
- 자동 run catalog: [`phases/RUN_CATALOG.csv`](phases/RUN_CATALOG.csv)
- storage 감사와 정책: [`docs/research/REPO_STORAGE_AUDIT.md`](docs/research/REPO_STORAGE_AUDIT.md), [`docs/research/PROPOSED_STORAGE_POLICY.md`](docs/research/PROPOSED_STORAGE_POLICY.md)

## 전환 영역

다음 경로는 새 정보를 넣는 표준 소유자가 아니다.

- `data/`: ignored local dataset/work volume. 외부 artifact backend 도입 전까지 원위치 보존한다.
- `results/`: 과거 compact evidence와 대용량 generated payload가 섞인 전환 영역이다. 검증된 compact 자료만 `docs/`로 승격했다.
- `reports/`: tracked 자료는 정본 owner로 승격했고, 남은 파일은 수정하지 않은 local runtime state다.
- `fair-pilot/`: 자체 config/script/doc/run을 함께 가진 과거 pilot bundle이다. embedded path와 외부 backend를 함께 해결하기 전에는 일괄 이동하지 않는다.
- `env/`, `runs/`: tracked migration은 끝났고 빈 물리 디렉터리만 남아 있다.
- `external/`: 승인된 third-party source 계약이 있을 때만 사용한다.
- `legacy/`: 현재 import 대상이 아닌 명시적 reference-code 격리 영역이다.

`artifacts/`는 아직 없다. 저장할 외부 backend, immutable URI, checksum, retention 계약 없이 빈 폴더나 payload 복사본부터 만들지 않는 것이 현재 정책이다.

## 실행 원칙

모든 연구 도구 실행은 Docker와 versioned config를 사용한다. 새 산출물은 역할에 따라 위 owner에 한 번만 저장하고, raw/generated payload를 `docs/`나 `phases/`에 복제하지 않는다. 단계별 추가 규칙은 해당 `phases/<phase>/AGENTS.md` 또는 `CLAUDE.md`를 따른다.
