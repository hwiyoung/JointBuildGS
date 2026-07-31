# Codex-to-Work Return Packet

- Template status: `DRAFT`

## Handoff metadata

- handoff_id:
- phase:
- direction: `Codex→Work`
- status: `READY_FOR_REVIEW`
- input_commit:
- output_commit:
- run_ids:
- completed_at:

## Executive summary

<!-- 수행 결과와 가장 중요한 제한을 간결히 기술한다. -->

## Completed tasks

- <fill>

## Artifacts

| Artifact | Resolver/path | Hash/config | Size/files | Verification level | Preview |
|---|---|---|---|---|---|

## Verification evidence

| Check | Command/method | Result | Evidence path |
|---|---|---|---|

## Findings

각 finding은 다음 중 하나를 사용한다.

- `VERIFIED`
- `PARTIAL`
- `UNKNOWN`
- `BLOCKED`

### Finding 1

- status:
- evidence:
- interpretation limit:
- recommended follow-up:

## Changes made

<!-- 파일별 변경과 scope를 기록한다. -->

## Deviations

<!-- packet에서 벗어난 항목. 없으면 None. -->

## Frozen-decision compliance

| Decision | Compliant | Evidence |
|---|---:|---|

## Unresolved issues

- <fill or None>

## Proposed phase status

`READY_FOR_REVIEW`

Codex는 `APPROVED` 또는 `CLOSED`를 제안·설정하지 않는다.

## Recommended next action

- <fill>

## Launcher prompt for Work

```text
<RETURN_PACKET_PATH>와 실제 artifact manifest를 교차검토하라.
finding의 evidence와 verification level을 확인한 뒤 연구적 의미와 한계를 해석하라.
필요하면 roadmap/contracts/Decision Log를 갱신하고 다음 packet은 DRAFT로 작성하라.
```
