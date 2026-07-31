# Handoff Index

- 문서 버전: `P1_AUDIT_v2`
- 작성일: 2026-07-31
- 저장소 유효 단계: `P2 / Fusion W1 ACTIVE`
- P1 지위: active P2를 변경하지 않는 read-only audit workstream

| Handoff ID | Phase | Direction | Packet version | Status | Source commit | Return packet | Superseded by | User approval |
|---|---|---|---:|---|---|---|---|---|
| `P1-W2C-REPO-AUDIT` | P1 | Work→Codex | v1 | `SUPERSEDED / TECHNICAL_BLOCKED@b08ee91` | `0e2270b238c6d14a61b781998e0cdc3319d9e64f` | `docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v1.md` | `P1-W2C-REPO-AUDIT-R2` | historical approval preserved |
| `P1-W2C-REPO-AUDIT-R2` | P1 | Work→Codex | v2 | `DRAFT` | `TO_BE_FILLED_BY_USER_BEFORE_APPROVAL` | `docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v2.md` | — | `NOT_GRANTED` |

## State rules

`DRAFT → APPROVED_FOR_EXECUTION → IN_PROGRESS → READY_FOR_REVIEW → CLOSED`

어느 상태에서도 새 packet이 승인되면 이전 packet은 `SUPERSEDED`로 보존한다.
v1 technical chain은 `offered → blocked`로 종료됐으며 재개하지 않는다. v2는
corrected source snapshot, approval commit, 새 R2 offered receipt와 activation
tuple이 모두 완성되기 전에는 실행할 수 없다.
