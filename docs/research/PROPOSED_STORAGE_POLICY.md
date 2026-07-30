# Proposed repository and artifact storage policy

## 상태와 목표

이 문서는 최종 7개 소유자 구조에 맞춘 **제안 정책**이며 2026-07-30 closeout `HEAD` `9e1ff575aa901b5873fc104bda61774e0fa58583`에서 재검증되었다. 삭제, `.gitignore` 변경, Git LFS migration, artifact upload, history rewrite를 승인하지 않는다.

목표는 코드·설정·검증·연구 계약·compact evidence·provenance를 Git에서 함께 검토하면서, raw/generated payload는 clone 경로 밖에서 manifest로 해석하는 것이다. 현재 sibling `../JointBuildGS-artifacts`는 local role separation을 구현했지만 durable backup이나 institutional artifact backend는 아니다.

## 7개 소유자의 저장 책임

| Root | 저장 책임 | 기본 등급 |
|---|---|---|
| `src/` | 재사용 알고리즘, pipeline, library, browser app source | A |
| `configs/` | 여러 run/phase가 재사용하는 parameter contract | A |
| `scripts/` | 재사용 실행기, 검증·inspection·repository maintenance workflow | A |
| `tests/` | 자동 검증과 작은 deterministic fixture | A; binary fixture는 별도 판단 |
| `docs/` | 연구 계약, 정본 보고서·표·지표, 검토 evidence, 선별 figure | A와 selected B |
| `phases/` | phase 전용 잠금 config/script, guide, compact run receipt | A; bulk payload 금지 |
| `artifacts/` | external payload를 해석하는 manifest와 schema | A; payload 자체는 C |

Root Docker/Compose/requirements 파일은 전역 실행 환경만 소유한다. `tools/`, `data/`, `results/`, `reports/`, `runs/`, `fair-pilot/`, `legacy/`, `external/`을 새 permanent owner로 다시 만들지 않는다.

## 분류 순서

확장자보다 역할을 먼저 본다.

1. cache, mutable state, rerunnable intermediate이면 **D**.
2. raw data, checkpoint, dense geometry/array, full render bundle, irreplaceable run payload이면 **C**.
3. checkout에서 path-addressable해야 하는 승인된 canonical binary evidence이며 allowlist owner가 있으면 **B**.
4. source/control-plane text, compact receipt, 작은 deterministic fixture이면 **A**.

불확실할 때 irreplaceable data는 C, 재생성 가능 output은 D가 기본이다. deadline 때문에 `git add -f`하는 것은 분류 근거가 아니다.

## A–D contract

| Class | 저장소 | 대표 내용 | 필수 metadata | 기본 획득 방식 |
|---|---|---|---|---|
| **A. regular Git** | ordinary Git blob | code, config, test, Markdown, compact CSV/JSON/YAML, manifest, receipt | producer/config/run link where relevant | normal 또는 sparse checkout |
| **B. selected Git LFS** | LFS pointer + LFS object | 승인된 final panel/figure/PDF, 고정 binary fixture의 작은 allowlist | provenance, license/access, owner/reviewer | selected LFS fetch |
| **C. external artifact storage + manifest** | immutable object/institutional storage | dataset, checkpoint, dense LAS/LAZ/PLY/mesh, full imagery, large array, run bundle | immutable URI, bytes, SHA-256, producer, source commit/config/container, CRS/access | manifest-driven hydration |
| **D. raw/generated/ignored data** | local scratch/work volume | cache, TensorBoard, temp panel, mutable log, preprocess intermediate, PID/lock, compiled local helper | nearby A-class run/config reference; durability promise 없음 | regenerate |

## Size와 aggregate gate

| 크기 | 제안 gate |
|---|---|
| `< 10 MiB` | A 가능. binary collection은 aggregate budget을 함께 검토한다. |
| `10–50 MiB` | binary는 A/B/C/D 결정을 review에 명시한다. canonical allowlist가 아니면 B로 보내지 않는다. |
| `50–100 MiB` | ordinary Git 기본 차단. 승인된 B 또는 C와 owner/provenance가 필요하다. |
| `>= 100 MiB` | C 기본. ordinary Git 금지. |
| `>= 1 GiB` | C only. checksum을 가진 chunk/archive로 관리한다. |

단일 파일 gate와 별도로 A/B 경로의 binary 증가가 100 MiB 이상이면 aggregate review를 요구한다. 현재 50 MiB tracked file은 0개지만 image 940개가 547.948 MiB이므로 이 gate가 필요하다.

## 경로·artifact별 기본값

| 대상 | 기본 등급 | 규칙 |
|---|---|---|
| `src/`, `configs/`, `scripts/`, `tests/`, root build files | A | 구현과 재현성 control을 Git에 보존 |
| `docs/research/**/*.md`, compact table/catalog | A | 연구 계약과 정본 지도 |
| `docs/experiments/` summary/metric/report | A | compact immutable result만 |
| `docs/evidence/`, `docs/figs/` binary | B 후보 | blanket pattern이 아니라 승인된 evidence set만 선별 |
| `phases/*/{configs,scripts,docs}`와 compact `runs/` receipt | A | phase 전용 잠금 절차와 provenance; payload 금지 |
| `artifacts/manifests/` | A | C payload resolver; workstation-only path를 durable URI처럼 표현하지 않음 |
| raw datasets, checkpoints, dense geometry, full-resolution imagery/arrays | C | external backend + manifest |
| raw run directories, mutable logs, caches, temp panels | D | 외부 work volume에서 실행하고 필요한 항목만 promote |

현재 tracked LAS/LAZ/PLY 27개와 phase raw log 일부는 historical policy debt다. 이 문서는 즉시 이동·삭제를 지시하지 않는다. 다음 curation review에서 tiny deterministic fixture 또는 canonical evidence인지 입증되지 않으면 C/D로 재분류한다.

## C-class manifest minimum

```yaml
schema_version: 1
artifact_id: <stable id>
role: <dataset|checkpoint|pointcloud|mesh|image-bundle|run-bundle>
uri: <durable immutable URI; workstation path is insufficient>
bytes: <integer>
sha256: <file or canonical archive digest>
created_at: <ISO-8601>
source:
  upstream_uri: <if applicable>
  license_or_access_class: <public|restricted|internal plus terms>
producer:
  git_commit: <40-hex>
  script: <repository path>
  config: <repository path>
  container_image: <tag and immutable digest>
spatial:
  crs: EPSG:25832
dependencies:
  - artifact_id: <input artifact>
validation:
  expected_files: <count>
  checks: <format/schema/domain checks>
retention: <canonical|recovery|temporary plus review date>
```

Directory는 deterministic archive 또는 sorted per-file path/size/hash ledger와 ledger hash를 사용한다. 이미 검증된 수백 GiB를 일상적으로 재해시하지 말고 creation-time hash를 보존한 뒤 routine reuse에서는 path/size/dependency gate를 우선한다.

## Run에서 정본으로 승격하는 흐름

1. 실행은 `JBGS_ARTIFACT_ROOT` 아래 C/D work area에 쓴다.
2. 완료 시 config, commit, image digest, metrics, issues, status를 compact A receipt로 `phases/<phase>/runs/<purpose>/<run_id>/`에 동결한다.
3. irreplaceable payload는 C backend에 업로드하고 immutable URI/checksum을 `artifacts/manifests/`에 기록한다.
4. 정본 report/table은 `docs/experiments/`, 검토 package는 `docs/evidence/`, 승인된 대표 figure만 `docs/figs/`로 promote한다.
5. clean partial/sparse checkout에서 A record를 읽고 C artifact를 원 workstation path 없이 resolve할 수 있어야 한다.

## Docker와 runtime contract

- Repository checkout mount와 artifact mount를 분리한다.
- runtime payload root는 `JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS`다.
- 과거 `data/`, `results/`, `reports/`, phase 내부 path를 다시 compatibility bind mount하지 않는다.
- frozen historical receipt 안의 과거 path 문자열은 snapshot provenance로 유지할 수 있다. active resolver/config만 현재 contract를 사용한다.

## Git LFS 도입 조건

현재 LFS pointer와 `.gitattributes`는 없다. 향후 B 도입은 별도 승인 task에서만 수행한다.

1. developer/CI에 pinned LFS client를 제공한다.
2. 모든 PNG 같은 blanket rule 대신 경로별 allowlist를 쓴다.
3. quota, retention, access, backup을 확인한다.
4. `GIT_LFS_SKIP_SMUDGE=1`, selected fetch, clone/checkout를 검증한다.
5. 기존 ordinary blobs는 history rewrite 없이는 사라지지 않음을 명시한다.

현재 history 최대 blob 32.341 MiB이므로 LFS를 이유로 history rewrite할 근거는 없다.

## 자동 gate 제안

향후 report-only CI에서 다음을 검출한다.

- ordinary Git blob `>= 50 MiB`;
- A/B binary 경로가 aggregate budget을 초과하는 변경;
- 승인되지 않은 LFS pointer/path;
- URI, bytes, SHA-256, commit, producer/config, access metadata가 없는 C manifest;
- runtime/cache path의 staging;
- absolute workstation path만 가진 active report/manifest;
- CRS가 빠진 geospatial artifact manifest;
- 7개 외의 permanent top-level owner 생성.

Checker는 보고만 하고 이동·삭제·history 수정은 자동 수행하지 않는다.

## Retention

- **Canonical:** 정책이 허용하는 두 개 이상의 독립 copy와 Git manifest.
- **Recovery:** 목적과 보존 기한을 명시하고 만료 시 review. 자동 삭제 금지.
- **Regenerable:** D-class local storage, reproducible script/config와 no durability claim.
- **Restricted/raw:** C backend access control과 license/provenance. ignored라는 이유로 backup되었다고 간주하지 않는다.

## 다음 승인 순서

1. A–D owner와 binary aggregate budget 승인.
2. C durable backend를 작은 bundle로 pilot하고 local sibling과 구분.
3. manifest resolver와 report-only CI gate 추가.
4. B allowlist와 LFS client/quota pilot.
5. stale ignore rule 검토는 별도 `.gitignore` task로 분리.
6. fresh partial/sparse clone acceptance test.
7. clean-clone 측정 후에만 history migration 필요성을 재평가.

이 정책 갱신에서는 위 작업을 실행하지 않았다.
