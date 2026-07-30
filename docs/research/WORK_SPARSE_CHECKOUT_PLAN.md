# Work sparse-checkout and partial-clone plan

## 결정

기존 repository의 **새 control-plane checkout**을 `--filter=blob:none` partial clone + cone-mode sparse checkout으로 만든다. 현재 active checkout은 진행 중인 Fusion index/worktree와 sibling artifact workspace를 보존하기 위해 in-place 변환하지 않는다.

- Partial clone은 접근하지 않은 Git blob download를 지연한다.
- Sparse checkout은 working tree에 나타나는 tracked path를 제한한다.
- 둘 다 external artifact hydration을 대신하지 않으며 기존 checkout의 ignored/untracked file을 제거하지 않는다.

측정 기준 current checkout은 `.git` 제외 733.891 MiB, `.git` 1.801 GiB이고 live remote tree는 732.360 MiB다. 가장 큰 단일 current blob은 9.987 MiB지만 tracked image aggregate가 547.948 MiB이므로 이 조합의 효과가 있다.

## 사전 조건

1. 현재 `JointBuildGS` checkout과 linked worktree를 그대로 둔다.
2. `git ls-remote`로 target branch를 확인한다. 2026-07-30 audit의 live `exp/fusion-w1`은 `97f6b3ef3159360b88ba0b25cca4b280c14fdcb8`이다.
3. pilot은 새 sibling directory에서만 실행한다.
4. remote가 blob filter를 지원하는지 확인한다.
5. C-class payload는 manifest와 필요 범위를 확인하기 전 hydration하지 않는다.
6. 현재 local branch는 remote보다 43 commits 앞서므로, push 전 pilot은 live remote 구조만 보인다는 점을 기록한다. 새 구조 acceptance test는 최종 구조 commit이 push된 뒤 다시 수행한다.

## Profile 1 — 최소 control plane

기본 개발·검토에 필요한 재사용 구현, 설정, 실행기, 테스트, manifest, 연구 계약만 포함한다.

```text
src/
configs/
scripts/
tests/
artifacts/manifests/
docs/research/
phases/p0-audit/{AGENTS.md,CLAUDE.md,issues.md,scripts/}
phases/p2-gsjso/{CLAUDE.md,configs/,docs/,scripts/}
```

Cone mode는 선택한 directory의 ancestor에 직접 위치한 파일도 유지하므로 root `AGENTS.md`, `README.md`, Docker/Compose/requirements와 phase guide가 실제로 존재하는지 pilot에서 확인한다.

새 checkout 전용 명령 예시:

```bash
git clone \
  --filter=blob:none \
  --no-checkout \
  --branch exp/fusion-w1 \
  git@github-hwiyoung:hwiyoung/JointBuildGS.git \
  JointBuildGS-control

cd JointBuildGS-control
git sparse-checkout init --cone
git sparse-checkout set \
  src configs scripts tests \
  artifacts/manifests \
  docs/research \
  phases/p0-audit/scripts \
  phases/p2-gsjso/configs \
  phases/p2-gsjso/docs \
  phases/p2-gsjso/scripts
git checkout exp/fusion-w1
```

실행 환경에서 `github-hwiyoung` SSH alias를 쓸 수 없으면 승인된 HTTPS URL 또는 해당 환경에 설정된 SSH host를 쓴다. credential을 repo에 복사하지 않는다.

## Profile 2 — 실험 문서 검토

Profile 1에 정본 report/table을 추가한다.

```bash
git sparse-checkout add docs/experiments
```

검토 package가 필요할 때만 구체 evidence family를 추가한다.

```bash
git sparse-checkout add docs/evidence/<review-package>
```

완료된 P0 audit의 evidence는 phase control과 분리되어 있으므로 다음 경로를 선택한다.

```bash
git sparse-checkout add docs/evidence/p0-audit
```

`docs/evidence` 전체나 `docs/figs` 전체를 기본 profile에 넣지 않는다. 대표 figure set만 경로 단위로 추가한다.

```bash
git sparse-checkout add docs/figs/<approved-evidence-set>
```

현재 `docs/figs`는 604 files / 361.506 MiB다. partial clone에서는 이 경로를 checkout하거나 파일을 열 때 blob이 on-demand fetch될 수 있다.

## Profile 3 — 한 phase run 검토

최종 구조의 run receipt는 연구 목적 아래 실행 단위로 찾는다.

```bash
git sparse-checkout add \
  phases/p2-gsjso/runs/<research-purpose>/<run_id>
```

이 경로에는 compact receipt만 있어야 한다. dataset/checkpoint/render/point-cloud payload는 해당 receipt가 참조하는 `artifacts/manifests/<manifest>.yaml`을 통해 별도 C backend로 resolve한다. `phases/p2-gsjso/runs` 전체를 습관적으로 추가하지 않는다.

## 검증 gate

Pilot checkout에서 다음을 기록한다.

```bash
git rev-parse HEAD
git rev-parse --is-shallow-repository
git config --get remote.origin.promisor
git config --get remote.origin.partialclonefilter
git config --get core.sparseCheckout
git config --get core.sparseCheckoutCone
git sparse-checkout list
git status --short --branch
git count-objects -vH
du -sb --exclude=.git .
du -sb .git
```

필수 결과:

- `HEAD`가 intended live origin SHA와 같다.
- partial clone은 shallow clone이 아니다.
- `remote.origin.promisor=true`, filter는 `blob:none` 또는 승인된 equivalent다.
- sparse checkout과 cone mode가 enabled다.
- 7개 permanent owner contract를 깨는 compatibility root가 생성되지 않는다.
- source/config/test의 control-plane validation이 bulk artifact 없이 가능하다.
- 원 dataset/result를 복사·이동·수정하지 않는다.

Normal clone과 비교할 항목은 clone wall time, network bytes, `.git` size, checked-out size, 첫 evidence/run path 추가 시 on-demand fetch bytes와 latency다.

## Artifact hydration contract

Sparse checkout은 artifact manager가 아니다. dataset/checkpoint가 필요한 run은 다음 순서를 따른다.

1. tracked C manifest를 읽는다.
2. access와 free space를 확인한다.
3. approved external/work volume으로만 다운로드한다.
4. bytes/hash, dependency, CRS를 검증한다.
5. `JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS`를 통해 Docker/config에서 resolve한다.
6. resolved artifact ID와 URI를 compact run receipt에 기록한다.

기존 `data/`, `results/`, `reports/`, phase payload tree를 새 checkout 안으로 재귀 복사하지 않는다. 과거 compatibility submount도 다시 만들지 않는다.

## 주의점

- history 전체 blob content를 읽는 Git 명령은 partial clone에서 대량 on-demand fetch를 일으킬 수 있다. metadata-only 점검을 우선한다.
- Sparse checkout은 이미 존재하는 ignored/untracked file을 숨기지 않으므로 반드시 새 directory에서 pilot한다.
- path가 sparse set에 포함되었다고 scientific input이 검증된 것은 아니다. C manifest gate가 별도로 필요하다.
- 향후 Git LFS를 도입하면 partial clone과 독립적으로 `GIT_LFS_SKIP_SMUDGE=1` 및 selected fetch를 시험한다.
- 현재 linked worktree는 shared Git config/object store를 사용하므로 pilot 대상으로 삼지 않는다.
- frozen historical evidence 안의 과거 path 문자열은 snapshot이다. sparse plan을 맞추기 위해 기계적으로 rewrite하지 않는다.

## Rollback과 재평가

Pilot은 새 checkout이므로 실패 시 사용을 중단하고 기존 checkout을 그대로 둔다. pilot directory 삭제도 별도 destructive task이며 이 계획에 포함되지 않는다.

다음 조건에서만 별도 ResearchControl repo를 재검토한다: 서로 다른 access control, 독립 release cadence, archival owner, publication boundary가 실제 요구사항으로 확정된 경우.

다음 조건에서만 history cleanup을 재검토한다: partial/sparse clean-clone 측정 후에도 transfer/storage가 허용 불가하거나 향후 50/100 MiB gate 위반 blob이 commit된 경우. 현재 감사 수치만으로는 history cleanup이 필요하지 않다.

이 계획은 실행되지 않았다.
