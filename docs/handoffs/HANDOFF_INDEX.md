# Handoff Index

- 문서 버전: `C1C5_CANON_v2`
- 작성일: 2026-07-31
- 저장소 유효 단계: `C1–C5 PROGRAM / GATE S0 FREEZE DRAFT / PERFORMANCE BLOCKED`
- P1 지위: audit evidence `READY_FOR_REVIEW`; technical chain closed

| Handoff ID | Phase | Direction | Packet version | Status | Source commit | Return packet | Superseded by | User approval |
|---|---|---|---:|---|---|---|---|---|
| `P1-W2C-REPO-AUDIT` | P1 | Work→Codex | v1 | `SUPERSEDED / TECHNICAL_BLOCKED@b08ee91` | `0e2270b238c6d14a61b781998e0cdc3319d9e64f` | `docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v1.md` | `P1-W2C-REPO-AUDIT-R2` | historical approval preserved |
| `P1-W2C-REPO-AUDIT-R2` | P1 | Work→Codex | v2 | `READY_FOR_REVIEW / TECHNICAL_CLOSED@8a6b5e61` | `939f0b97825eafb7e508239b9c5510938e30fa9f` | `docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v2.md` | — | historical execution approval |
| `P2-W2C-GATE-S0-PREP-v1` | P2/S0 | Work→Codex | v1 | `BLOCKED_FOR_GATE_S0_REVIEW / TECHNICAL_CLOSED@1cf0db33` | `0716c925b43aa401ced47f2311ca28663b290a44` | `docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md` | — | `GRANTED — 2026-07-31` |
| `P2-W2C-GATE-S0-REMEDIATION-R1-v1` | P2/S0 | Work→Codex | v1 | `BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW / TECHNICAL_CLOSED@052f7d5c` | `0928201553ba414109ae1f547a8e18a0be38b3d4` | `docs/handoffs/returns/P2_C2W_GATE_S0_REMEDIATION_R1_RETURN_v1.md` | — | `GRANTED — 2026-07-31` |
| `P2-W2C-GATE-S0-EVIDENCE-R2A-v1` | P2/S0 | Work→Codex | v1 | `BLOCKED_FOR_GATE_S0_EVIDENCE_REVIEW / TECHNICAL_CLOSED@00181afc` | `7277de4f48c4a5eededb00957c529e9f192e48b0` | `docs/handoffs/returns/P2_C2W_GATE_S0_EVIDENCE_R2A_RETURN_v1.md` | — | `GRANTED — 2026-08-01` |
| `P2-W2C-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1` | P2/S0 | Work→Codex | v1 | `DRAFT SOURCE SNAPSHOT / USER APPROVED` | `TO_BE_FILLED_BY_APPROVAL_COMMIT` | `docs/handoffs/returns/P2_C2W_GATE_S0_COMMON_BASE_LINEAGE_R2B_RETURN_v1.md` | — | `GRANTED — 2026-08-01` |

## State rules

`DRAFT → APPROVED_FOR_EXECUTION → IN_PROGRESS → READY_FOR_REVIEW → CLOSED`

어느 상태에서도 새 packet이 승인되면 이전 packet은 `SUPERSEDED`로 보존한다.
P1 v1 technical chain은 `offered → blocked`로 종료됐으며 재개하지 않는다. P1 R2,
Gate S0 preparation v1과 remediation R1은 각각 `offered → accepted → verified → closed`로
종료됐고 writer 순번이 Work Host에 반환됐다. 기술 완료는 Gate 승인이 아니다.
`GATE_S0_FREEZE_PACKET_v1.md`는 human-review DRAFT이며 handoff가 아니다. Evidence
completion 또는 performance 실행에는 각각 별도 승인 Task Packet과 새 handoff ID가
필요하다.
