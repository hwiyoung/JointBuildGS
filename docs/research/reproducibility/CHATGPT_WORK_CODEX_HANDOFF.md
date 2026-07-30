# ChatGPT Work–Codex two-host handoff contract

## 목적과 정본

JointBuildGS는 코드·연구 문서 작업과 대용량 실험 실행을 서로 다른 host에서
수행한다. 이 문서는 두 host 사이의 쓰기 소유권, Git handoff, artifact 주장,
검증 수준을 고정한다.

| 이름 | 역할 | 정본 |
|---|---|---|
| **Work Host** | 코드, config, preregistration, 계획, 리뷰 | GitHub `main`의 Git content |
| **Experiment Host** | 정확한 commit을 Docker로 실행하고 compact result를 작성 | GitHub `main` + local Artifact Store |
| **GitHub Origin** | 양 host가 교환하는 코드·문서 정본 | durable branch `main` |
| **Artifact Store** | dataset, checkpoint, render, point cloud, mesh, full log | `JointBuildGS-artifacts` |
| **Recovery Checkout** | 과거 dirty WIP 복구 | 활성 작업 금지, handoff source 금지 |

GitHub는 raw payload 정본이 아니고 Artifact Store는 코드 정본이 아니다. Work
Host가 payload를 직접 보지 못한 경우 Experiment Host의 receipt를 검토할 수는
있지만 독립적으로 재검증했다고 주장할 수 없다.

## 현재 transport mode

한 명의 연구자와 두 agent host가 순차 작업하므로 기본 mode는
`serialized_main`이다.

1. 한 시점에 오직 한 host만 write owner다.
2. sender가 push한 뒤 receiver가 exact `origin/main` SHA를 fetch한다.
3. receiver는 handoff manifest를 검증하기 전 파일을 수정하거나 실험하지 않는다.
4. receiver가 compact 결과를 push하기 전 Work Host는 새 write를 시작하지 않는다.
5. v1 contract는 `serialized_main`만 허용한다. 동시 branch/PR transport는 remote
   ref와 review evidence를 강제하는 별도 schema version이 생기기 전에는 사용하지 않는다.

Durable remote branch는 `main` 하나를 유지한다. `serialized_main`은 단순한
직접 push 허용이 아니라 manifest의 `exclusive_writer_ack=true`, base ancestry,
remote-head 일치를 모두 통과해야 하는 단일-writer protocol이다.

## Handoff 상태

```text
offered -> accepted -> verified -> closed
                    \-> blocked
```

- `offered`: sender가 scope와 exact commit을 게시했다.
- `accepted`: receiver가 base/head/scope를 확인하고 write owner를 넘겨받았다.
- `verified`: 선언한 Git-only 또는 artifact-aware gate가 통과했다.
- `blocked`: 실패를 숨기지 않고 blocker와 미실행 범위를 기록했다.
- `closed`: compact result와 issues가 Git에 있고 write owner가 반환됐다.

각 상태는 **새 immutable receipt 파일**이다. 기존 파일을 `offered`에서
`accepted`로 수정하지 않는다. `offered` 이외 receipt는 `previous_receipt`의
path와 SHA-256으로 직전 immutable event를 연결하며, validator가 허용된 상태
전이, strict Git commit ancestry, 단조 증가 event timestamp를 검사한다. 모든
receipt와 dirty-WIP snapshot 구성요소는 한 번 추가된 뒤 수정·삭제·재추가할 수 없다.
각 receipt commit은 현재 `handoff_id` 디렉터리 안에 event JSON 하나만 추가할
수 있으며, 다른 handoff의 receipt나 snapshot 파일을 함께 수정·삭제·rename할
수 없다.

Receipt 위치와 이름은 다음으로 고정한다. 같은 `handoff_id` 아래 offered root는
정확히 하나여야 한다.

```text
artifacts/manifests/handoffs/<handoff_id>/000-offered.json
artifacts/manifests/handoffs/<handoff_id>/100-accepted.json
artifacts/manifests/handoffs/<handoff_id>/200-verified.json  # 또는 200-blocked.json
artifacts/manifests/handoffs/<handoff_id>/300-closed.json
```

각 event가 한 operational task/commit이다. 연구 작업의 안정된 `task_id`는
handoff lifecycle 전체에서 유지하지만 commit message에는 event state도 기록한다.

각 방향의 실제 handoff는
`artifacts/manifests/templates/two_host_handoff.json`을 복사해 immutable task
receipt로 만든다. `current_handoff.json` 같은 가변 전역 파일은 만들지 않는다.

## Work Host -> Experiment Host

1. Work Host는 최신 `origin/main`에서 시작하고 `base_main`을 기록한다.
2. 허용 경로와 보호 경로를 manifest에 고정한다.
3. code/config/preregistration 변경과 handoff receipt를 한 task commit으로 만든다.
   같은 commit을 뜻할 때 `offered_head`는 `SELF`를 사용한다.
4. Docker로 Git-only tests를 실행하고 commit을 만든다. Commit 후·push 전에는
   `--origin-ref HEAD`, push 후에는 기본 `origin/main`으로 handoff validator를
   각각 실행한다. Validator는 manifest bytes가 실제 receipt commit과 같은지,
   `base_main..receipt_head`의 변경 경로가 scope 안인지 검사한다.
5. Experiment Host는 `git fetch origin main` 후 manifest의 exact head만 받는다.
6. stale base, scope overlap, artifact 접근 불가, lock 불일치가 있으면 실행하지
   않고 `blocked` receipt를 반환한다.

Work Host는 로컬 SSH alias, credential, `.env`, raw data를 repo에 복사하지 않는다.

## Experiment Host -> Work Host

1. Experiment Host는 accepted SHA와 config를 run receipt에 기록한다.
2. 모든 project tool과 test는 repository Docker image에서 실행한다.
3. payload는 새 run namespace에 쓰며 기존 완료 artifact를 덮어쓰지 않는다.
4. Git에는 compact CSV/JSON/Markdown, manifest, receipt, issue만 넣는다.
5. point cloud, mesh, image bundle, checkpoint, cache, full log는 Artifact Store에
   유지하고 URI, bytes, SHA-256을 compact manifest에 기록한다.
6. v1에서 기존 receipt/hash를 읽기만 한 provenance review는 `git_only`다.
   `artifact_verified`는 `--artifact-root` 아래 실제 payload의 bytes와 SHA-256을
   다시 읽어 일치시켰을 때만 사용한다. Work Host의 검토는 이 주장을 새로
   생성하지 않는다.
   과거 chain에 `artifact_verified`가 하나라도 있으면 후속 receipt가 이를
   `git_only`로 낮추거나 record를 바꿀 수 없으며, validator는 과거 payload도
   `--artifact-root`에서 다시 해시한다.
7. 기술 gate와 과학적 승격을 분리한다. 사람 승인 전
   `scientific_verdict`는 항상 `null`이다.

## 필수 receipt 필드

- `handoff_id`, `task_id`, direction, sender/receiver role, state
- `base_main`, `offered_head`, immutable `receipt_head`, serialized-main acknowledgement
- allowed/protected path, dirty-WIP snapshot 필요 여부
- verification level, verifier role, Docker image digest, commands, test counts
- host별 artifact availability와 각 output의 URI, bytes, SHA-256, verification method
- technical state와 `scientific_verdict: null`
- 직전 immutable receipt path/SHA와 accepted/blocked/closed receiver acknowledgement

Schema는
[`two_host_handoff.schema.json`](../../../artifacts/manifests/schemas/two_host_handoff.schema.json),
검증기는
[`validate_two_host_handoff.py`](../../../scripts/repository/validate_two_host_handoff.py)다.

```bash
python scripts/repository/validate_two_host_handoff.py \
  artifacts/manifests/<immutable-handoff>.json
```

Commit 후·push 전 검증에서는 아직 `origin/main`이 새 commit을 가리키지 않으므로
`--origin-ref HEAD`를 사용한다. Staged 상태를 `SELF`로 가장하는 pre-commit
검증은 허용하지 않는다. Push 후와 receiver acceptance에서는 기본
`origin/main` 검증을 다시 실행한다.

## Fail-closed 규칙

- manifest에 없는 경로는 수정하지 않는다.
- `dirty_wip=false`이면 index, working tree, untracked path가 모두 비어야 한다.
- allowed/protected scope가 겹치면 handoff를 거부한다.
- exact commit이나 artifact hash가 없으면 같은 이름의 다른 파일로 대체하지 않는다.
- Work Host의 `git_only` 검증을 `artifact_verified`로 승격하지 않는다.
- dirty WIP를 전달할 때는 복구 rehearsal을 통과한 snapshot manifest가 필수다.
- dirty-WIP snapshot은 일반 파일이나 자기선언 문자열로 대체할 수 없다.
  `local_wip_snapshot.schema.json`, base commit, staged/unstaged/untracked ledger,
  category별 실제 Git 상태, component bytes/hash, current WIP bytes, working-file
  tar inventory, restore counts가 모두 맞아야 한다. Validator가 base commit의
  격리 clone에서 staged patch, unstaged patch, working tar를 직접 재생하고 최종
  porcelain-v2 상태와 path별 bytes/hash를 비교한다.
- `verified`/`closed`는 Docker digest, command, tests, zero failure를 요구한다.
- 실패한 실행은 issue와 receipt에 남기며 성공으로 축약하지 않는다.
- 기술 완료는 과학적 판정이 아니다.

## Bootstrap과 clone

Work Host는 승인된 GitHub URL을 환경별로 제공받아 `main`만 partial clone한다.
현재 operator host의 SSH alias를 다른 컴퓨터에 복사하지 않는다. 정확한
partial/sparse profile과 acceptance gate는
[`WORK_SPARSE_CHECKOUT_PLAN.md`](../WORK_SPARSE_CHECKOUT_PLAN.md)를 따른다.
