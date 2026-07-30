# Work sparse-checkout and partial-clone plan

## 결정

ChatGPT Work는 GitHub `main`의 **새 독립 checkout**을 `--filter=blob:none`
partial clone + cone-mode sparse checkout으로 사용한다. 기존 Fusion recovery
checkout이나 linked worktree를 Work Host에 복사하지 않는다.

- Partial clone은 접근하지 않은 Git blob download를 지연한다.
- Sparse checkout은 working tree에 나타나는 tracked path를 제한한다.
- 둘 다 external artifact hydration이나 backup을 대신하지 않는다.
- Durable remote branch는 `main` 하나이며 삭제된 `exp/fusion-w1`을 clone하지 않는다.

## 원격 identity gate

Work Host마다 승인된 URL을 환경변수로 제공한다. Experiment Host의 SSH alias나
credential을 repository로 복사하지 않는다.

```bash
JBGS_REMOTE_URL="${JBGS_REMOTE_URL:?approved GitHub URL required}"
git ls-remote --symref "$JBGS_REMOTE_URL" HEAD refs/heads/main
git ls-remote --heads "$JBGS_REMOTE_URL"
```

필수 결과:

- symbolic `HEAD`는 `refs/heads/main`이다.
- remote head는 `main` 하나다.
- remote identity는 승인된 `hwiyoung/JointBuildGS`다.
- 감사를 고정한 SHA와 다르면 자동 수용하지 않고 handoff를 다시 검증한다.

## Work acceptance profile

기본 profile은 source/config/test뿐 아니라 `validate_work_readiness.py`가 직접
읽는 canonical documents와 reviewed reference target을 포함한다.

```bash
git clone \
  --filter=blob:none \
  --no-checkout \
  --single-branch \
  --branch main \
  --no-tags \
  "$JBGS_REMOTE_URL" \
  JointBuildGS-work

cd JointBuildGS-work
git sparse-checkout init --cone
git sparse-checkout set \
  src configs scripts tests \
  artifacts/manifests \
  docs/research \
  docs/experiments \
  docs/evidence/archive \
  docs/evidence/p0-audit \
  docs/evidence/p0_g1_20260613 \
  docs/figs/stage3_polyfit_phase2 \
  docs/figs/tum2twin_surface_proxy_rv1 \
  docs/figs/W_D6 \
  docs/figs/W_matched_rms \
  docs/figs/boundary_map \
  docs/figs/phase2_synthesis \
  docs/figs/tum_transfer \
  docs/figs/W_D4_qual \
  phases/p0-audit/env \
  phases/p0-audit/scripts \
  phases/p2-gsjso/configs \
  phases/p2-gsjso/docs \
  phases/p2-gsjso/scripts
git checkout main
```

Cone mode가 ancestor의 root files를 포함하므로 `AGENTS.md`, `CLAUDE.md`,
`README.md`, Docker/Compose/requirements와 phase README가 존재해야 한다.

## 단계별 확장

특정 evidence package, figure family, compact run receipt가 필요할 때만 추가한다.

```bash
git sparse-checkout add docs/evidence/<review-package>
git sparse-checkout add docs/figs/<approved-evidence-set>
git sparse-checkout add phases/p2-gsjso/runs/<research-purpose>/<run_id>
```

Run path에는 compact receipt만 있어야 한다. dataset, checkpoint, render bundle,
point cloud, mesh는 tracked manifest의 URI로 Artifact Store에서 resolve한다.

## Git-only acceptance gate

```bash
git rev-parse HEAD
git rev-parse origin/main
git rev-parse --is-shallow-repository
git config --get remote.origin.promisor
git config --get remote.origin.partialclonefilter
git config --get remote.origin.tagOpt
git config --get core.sparseCheckout
git config --get core.sparseCheckoutCone
git sparse-checkout list
git status --short --branch
GIT_NO_LAZY_FETCH=1 git rev-list --objects --all --missing=print
```

필수 결과:

- `HEAD == origin/main ==` handoff의 exact offered head다.
- shallow clone이 아니고 promisor는 `true`, filter는 `blob:none`이다.
- tag fetch는 비활성이고 archive tag가 Work clone에 들어오지 않는다.
- sparse/cone mode가 켜져 있고 working tree는 clean이다.
- 제외 blob 일부가 `?`로 남아 partial clone 효과가 유지된다.
- 7개 permanent owner 이외 compatibility root를 만들지 않는다.

Artifact를 mount하지 않은 read-only container에서 다음을 실행한다.

```bash
python scripts/repository/validate_agent_instructions.py
python scripts/repository/validate_work_readiness.py
python -m unittest tests.repository.test_agent_instruction_sync
python -m unittest tests.repository.test_two_host_handoff
```

Git-only readiness는 PASS여야 한다. 반대로 존재하지 않는 artifact root를
지정한 검증과 Fusion payload rehash는 실패해야 정상이다. Work Host는 이 실패를
payload 검증 성공으로 대체하거나 같은 이름의 다른 파일을 찾지 않는다.

## Artifact-aware Experiment Host

Experiment Host는 normal working tree 또는 필요한 scope가 모두 포함된 sparse
checkout에서 다음을 추가 검증한다.

1. `JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS`가 실제 backend를 가리킨다.
2. bytes/hash/dependency/CRS를 검증한다.
3. Docker image digest, command, config, input/output artifact를 receipt에 기록한다.
4. 기존 완료 payload를 덮어쓰지 않고 새 run namespace만 쓴다.
5. `artifact_verified` handoff는 Experiment Host만 생성한다.

## Inventory 제약

`repo_inventory.py`는 sparse에서 제외된 문서를 Git object가 아니라 working-tree
파일로 읽는다. 새 문서나 run receipt를 추가한 Work clone에서 catalog를 갱신할
때는 다음 중 하나를 사용한다.

1. 일시적으로 `git sparse-checkout add docs phases` 후 inventory를 생성·검증한다.
2. normal integration checkout에서 inventory를 생성·검증한다.

이를 생략하면 `RUN_CATALOG.csv`, `DOCUMENT_CATALOG.csv`,
`DOCUMENT_LINEAGE.csv`가 새 handoff와 어긋날 수 있다.

`validate_work_readiness.py`는 이 차이를 명시적으로 처리한다. Normal integration
checkout에서는 전체 inventory를 다시 스캔한다. Sparse Work clone에서는 전체
tree를 가장하지 않고, integration gate가 커밋한 `CATALOG_ISSUES.md`의 zero-
unclassified marker와 reviewed reference-resolution ledger를 검증한다.

## Artifact hydration 금지선

Sparse checkout은 artifact manager가 아니다. C-class payload는 tracked manifest를
먼저 읽고 approved external volume으로만 hydration한다. repo 안에 `data/`,
`results/`, `reports/`, phase payload compatibility tree를 재생성하지 않는다.

## 측정 상태

2026-07-30에 standalone operator partial clone은 `blob:none`, single branch
`main`으로 생성됐고 Git-only/local-artifact readiness, Fusion exact 157 tests,
repository tests를 통과했다.

같은 날 GitHub `main`의 `109f3e43f61768bd0bd2b040dd750700d9da7760`에서
새 independent Work acceptance clone을 위 23-path profile 그대로 생성했다.

| 측정 | 결과 |
|---|---:|
| `.git` disk usage | 67,067,012 bytes (65 MiB 표시) |
| sparse working tree | 148,266,675 bytes (147 MiB 표시) |
| working-tree regular files | 2,141 |
| promisor에서 아직 받지 않은 object lines | 6,823 |
| local/remote heads | `main` / `origin/main`만 존재 |
| fetched tags | 0 |

`HEAD == origin/main`, non-shallow, promisor `true`, filter `blob:none`, tagOpt
`--no-tags`, sparse/cone `true`, clean status를 확인했다. Artifact를 mount하지 않은
read-only/network-none container에서 agent contract, Git-only readiness, repository
68 tests가 통과했다. 존재하지 않는 artifact root를 지정한 readiness와 Fusion
payload rehash는 각각 nonzero로 실패하여 Work Host가 artifact 검증을 가장하지
않는 fail-closed 동작도 확인했다.

## 재평가 조건

Partial/sparse 측정 후에도 transfer/storage가 허용 불가하거나 새로운 50/100MiB
tracked blob이 생길 때만 history cleanup을 재검토한다. 별도 ResearchControl repo는
access control, release cadence, publication boundary가 실제로 분리될 때만 검토한다.
