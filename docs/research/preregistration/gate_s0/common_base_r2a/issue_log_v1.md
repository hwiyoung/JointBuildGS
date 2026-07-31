# Gate S0 Evidence R2A issue log v1

- task_id: `P2-GATE-S0-EVIDENCE-R2A-v1`
- proposed_status: `BLOCKED_FOR_GATE_S0_EVIDENCE_REVIEW`
- scientific_verdict: null
- performance_authority: `NONE`

## Findings

| ID | State | Finding | Next idempotent action |
|---|---|---|---|
| R2A-I01 | `REUSED_EXACT` | Exact R1 sparse member evidence is reusable, but one canonical converted derivative or an explicit bound-member consumption contract is still absent. | Execute the shared `sfm_sparse` DAG node once after Gate review; do not repeat R1 member hashing. |
| R2A-I02 | `AMBIGUOUS` | `data/work/mvs/openmvs/scene.mvs` exists but has no exact-937-base producer/config/member/frame binding; its content was not read or hashed. The 1,104-image vendor MVS is separately context-only and ineligible. | Resolve the unbound candidate lineage first; otherwise select producer/config/frame in a later approved preprocessing task and execute the shared node once. |
| R2A-I03 | `MISSING` | Exact-base depth is not bound. | Generate only after the shared dense-MVS identity is frozen. |
| R2A-I04 | `MISSING` | Exact-base normal evidence is not bound. | Generate only under the shared DAG and record orientation/frame. |
| R2A-I05 | `MISSING` | Exact-base image-derived confidence is not bound. | Keep confidence definition null until human review; separate it from external-prior confidence. |
| R2A-I06 | `DIAGNOSTIC_ONLY` | LoD2-derived LoD1 is self-conditioned against the same reference lineage. | Keep `primary_c5_eligible=false`; do not place it in primary C5, E_paired or Delta_N_pass(C5). |
| R2A-I07 | `BLOCKED` | Gate S0, U_target/E_paired, split, component enablement and performance remain unfrozen. | Human Gate S0 evidence review after this return. |

## Duplicate-work guard

- Closed R1 15.7 GB inputs, `Images.zip`, `opf.zip` and R1 sparse members were not rehashed.
- Dense MVS, depth, normal and confidence were not generated.
- Bounded discovery used directory entries and file metadata only; content-read bytes: `0`, hashed bytes: `0`.
- Bounded unbound filename candidates: `1`.
- Each LoD2 source was consumed once by the processing-and-digest stream.
- New LoD1 outputs await exactly one pre-push and one post-push first-artifact-receipt safety pass; `300-closed` must not rehash them.

## Prohibited activity attestation

No C1-C5 performance, GS training, Roofer comparison, held-out, Fusion W1 or `R_ext`
path was read, executed or written. No existing external file was overwritten or deleted.
