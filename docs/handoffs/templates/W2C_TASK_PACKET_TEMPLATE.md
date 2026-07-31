# Work-to-Codex Task Packet

## Handoff metadata

- handoff_id:
- phase:
- direction: `Work→Codex`
- status: `DRAFT`
- packet_version:
- source_commit: `TO_BE_FILLED_BY_USER_BEFORE_APPROVAL`
- target_branch:
- research_charter_version:
- master_roadmap_version:
- result_contract_version:
- data_scope_version:
- decision_log_through:
- supersedes:
- created_at:
- user_approval: `NOT_GRANTED`

## Goal

<!-- 하나의 검증 가능한 결과를 기술한다. -->

## Scientific context

<!-- RQ, hypothesis, 현재 phase와의 연결을 기술한다. -->

## Authoritative documents

1. root `AGENTS.md`
2. exact approved charter/decision/roadmap/contracts
3. exact active lock/preregistration

## Current frozen decisions

<!-- 이 task가 변경할 수 없는 결정과 Decision ID를 열거한다. -->

## Inputs

| Input | Version/hash | Resolver/path | Role | Verification |
|---|---|---|---|---|

## In scope

- <fill>

## Out of scope

- <fill>

## Tasks

1. <fill>

## Required outputs

| Output | Path | Required content |
|---|---|---|

## Verification

- exact commands/tests:
- required evidence:
- artifact verification level:

## Preflight

- [ ] User supplied the complete activation tuple:
      `handoff_id`, exact `offered_receipt_commit_sha`, `packet_path`,
      non-placeholder `source_commit`, and
      `explicit_user_authorization: APPROVED_FOR_EXECUTION`
- [ ] Experiment Host started from a clean checkout with no unpushed WIP
- [ ] `origin/main` was fetched and matched the advertised offered-receipt SHA
- [ ] Before pull, the packet and offered receipt at that remote commit were inspected
      read-only; packet status and user approval were `APPROVED_FOR_EXECUTION`,
      source commit matched the activation tuple, receipt `base_main` pinned the
      approval commit, and scope/receiver matched
- [ ] local main was updated with `git pull --ff-only origin main` to that exact SHA
- [ ] the offered receipt passed validation and an immutable accepted receipt transferred write ownership
- [ ] status is `APPROVED_FOR_EXECUTION`
- [ ] source commit is an exact non-placeholder ancestor/base snapshot
- [ ] approved research documents have not drifted from that source snapshot
- [ ] charter/roadmap/result/data versions match
- [ ] decision log is current
- [ ] no newer packet exists
- [ ] phase matches
- [ ] root instructions and active locks permit the scope
- [ ] target branch and current write owner match the packet
- [ ] required external artifacts resolve at the claimed verification level
- [ ] dirty WIP is absent or covered by an immutable validated snapshot
- [ ] `scripts/repository/validate_two_host_handoff.py` passes those ownership/artifact/WIP checks

If any item fails, return `STALE_TASK_PACKET` without executing.

## Stop conditions

- authority/version mismatch
- input/checksum/CRS ambiguity that can change the result
- protected-scope overlap
- required artifact cannot be resolved at the claimed verification level
- need for a scientific decision outside packet authority

## Done when

- <fill>

## Return packet path

`docs/handoffs/returns/<RETURN_PACKET>.md`

## Launcher prompt

```text
먼저 사용자가 handoff_id, exact offered-receipt SHA, packet path,
non-placeholder source_commit,
explicit_user_authorization: APPROVED_FOR_EXECUTION을 모두 제공했는지 확인하라.
하나라도 없으면 어떤 command도 실행하지 말고
DRAFT_OR_UNAUTHORIZED_HANDOFF를 반환하라.

승인 tuple이 완전할 때만 Experiment Host의 clean state를 확인하고
origin/main을 fetch하라. advertised offered-receipt SHA가 origin/main과
일치하는지 확인한 다음, pull 전에 remote commit의 packet과 receipt를
read-only로 검사하라. packet status와 사용자 승인이
APPROVED_FOR_EXECUTION이고 source_commit이 tuple과 일치하는
non-placeholder 값이며 receipt의 base_main/scope/receiver와 approval tree의
exact packet이 activation tuple과 일치할 때만
git pull --ff-only origin main으로 exact commit을 반영하라.
offered manifest를 검증하고 accepted receipt로 write ownership을 인수하기 전에는
task action을 시작하지 마라.
승인된 <TASK_PACKET_PATH>를 읽어라.
root AGENTS.md와 packet의 preflight를 먼저 적용하라.
불일치하면 실행하지 말고 STALE_TASK_PACKET으로 중단하라.
일치하면 In scope만 수행하고 required outputs와 Return Packet을 작성하라.
과학적 verdict나 phase approval을 임의로 내리지 마라.
```
