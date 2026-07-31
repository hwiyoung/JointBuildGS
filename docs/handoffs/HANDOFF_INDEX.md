# Handoff Index

- 문서 버전: `P1_AUDIT_v1`
- 작성일: 2026-07-31
- 저장소 유효 단계: `P2 / Fusion W1 ACTIVE`
- P1 지위: active P2를 변경하지 않는 read-only audit workstream

| Handoff ID | Phase | Direction | Packet version | Status | Source commit | Return packet | Superseded by | User approval |
|---|---|---|---:|---|---|---|---|---|
| `P1-W2C-REPO-AUDIT` | P1 | Work→Codex | v1 | `DRAFT` | `TO_BE_FILLED_BY_USER_BEFORE_APPROVAL` | `docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v1.md` | — | `NOT_GRANTED` |

## State rules

`DRAFT → APPROVED_FOR_EXECUTION → IN_PROGRESS → READY_FOR_REVIEW → CLOSED`

어느 상태에서도 새 packet이 승인되면 이전 packet은 `SUPERSEDED`로 보존한다.
현재 P1 audit scope는 사용자가 승인했지만 packet은 source/approval/offered commits가
없어 아직 실행할 수 없다.
