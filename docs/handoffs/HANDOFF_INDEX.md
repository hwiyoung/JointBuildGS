# Handoff Index

- 문서 버전: `C1C5_CANON_v1`
- 작성일: 2026-07-31
- 저장소 유효 단계: `C1–C5 PROGRAM / GATE S0 PREPARATION`
- P1 지위: audit evidence `READY_FOR_REVIEW`; technical chain closed

| Handoff ID | Phase | Direction | Packet version | Status | Source commit | Return packet | Superseded by | User approval |
|---|---|---|---:|---|---|---|---|---|
| `P1-W2C-REPO-AUDIT` | P1 | Work→Codex | v1 | `SUPERSEDED / TECHNICAL_BLOCKED@b08ee91` | `0e2270b238c6d14a61b781998e0cdc3319d9e64f` | `docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v1.md` | `P1-W2C-REPO-AUDIT-R2` | historical approval preserved |
| `P1-W2C-REPO-AUDIT-R2` | P1 | Work→Codex | v2 | `READY_FOR_REVIEW / TECHNICAL_CLOSED@8a6b5e61` | `939f0b97825eafb7e508239b9c5510938e30fa9f` | `docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v2.md` | — | historical execution approval |
| `P2-W2C-GATE-S0-PREP-v1` | P2/S0 | Work→Codex | v1 | `APPROVED_FOR_EXECUTION / OFFER_PENDING` | `0716c925b43aa401ced47f2311ca28663b290a44` | `docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md` | — | `GRANTED — 2026-07-31` |

## State rules

`DRAFT → APPROVED_FOR_EXECUTION → IN_PROGRESS → READY_FOR_REVIEW → CLOSED`

어느 상태에서도 새 packet이 승인되면 이전 packet은 `SUPERSEDED`로 보존한다.
P1 v1 technical chain은 `offered → blocked`로 종료됐으며 재개하지 않는다. P1 R2는
`offered → accepted → verified → closed`로 종료됐고 writer 순번이 Work Host에
반환됐다. Gate S0 packet의 source snapshot과 approval은 고정됐지만 offered/accepted
receipts와 activation tuple이 모두 완성되기 전에는 실행할 수 없다.
