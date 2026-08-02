# Codex-to-Work Return — P2 C1/C2 qualitative layout correction R2 v1

## Return metadata

- handoff_id: `P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R2-v1`
- task_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R2-v1`
- source implementation commit: `9ac8e85ffa116d5807e881a95086e3dce3e571e2`
- activation commit: `f5a50a73e678ea6bf5d89a2ab4dcee2fa2f95315`
- offered commit: `80b171ee67e18c891d114e5ff72e5ce5834ea325`
- accepted commit: `42e0bdc281954cd785c882fc23bef0291f1cb494`
- Return / 200-blocked commit: `SELF`
- 300-closed commit: `PENDING_DIRECT_CHILD_EVENT`
- run_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R2-RUN-v1`
- project image: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- completed_at: `2026-08-02T18:58:16+09:00`
- proposed technical status: `BLOCKED_AUTHORITY_PARSER_PACKET_FIELD_MISMATCH`
- scientific_verdict: `null`

## Answer first

The R2 task did not reach rendering. The literal direct invocation failed with exit
126 because the exact source launcher is Git mode `100644`; it did not enter the
launcher body. Under the subsequent explicit orchestration correction, the exact
same frozen body was invoked once through Bash. That sole body execution fetched
`origin/main`, proved the clean accepted HEAD/config tuple, and then stopped with exit
2 at the committed execution-authority parser before accepted-receipt validation,
artifact-file access, namespace creation, rendering, promotion, or PNG write.

The exact blocker is a contract mismatch in the protected source. The shared parser
accepts only these two literal packet lines:

```text
- status: `APPROVED_FOR_EXECUTION`
- user_approval: `APPROVED_FOR_EXECUTION`
```

The activated R2 packet instead contains:

```text
- status: `ACTIVATED_FOR_EXECUTION`
- explicit_user_authorization: `APPROVED_FOR_EXECUTION`
```

The parser therefore returned 64 and the launcher emitted
`task packet is not activated`. No protected source was edited or chmodded and the
launcher was not rerun.

## Ownership and immutable acceptance

- The full pre-pull procedure passed against Git objects before the exact
  fast-forward to offered commit `80b171ee67e18c891d114e5ff72e5ce5834ea325`.
- The predecessor 300 Git blob digest was
  `7fc0770501eb3447733b481fe7ccf195064cdb3cb35934744a8db2fca6d0ec64`.
- Its ordered artifact object contained 25 records and 30,432,763 bytes with
  canonical identity
  `903b0f744c982f83106099ba280ca98d5fb362cc77867f301a31183a30bb804c`.
- Add-once accepted commit `42e0bdc281954cd785c882fc23bef0291f1cb494`
  inherited that exact object via `closed_attestation_reuse`.
- Canonical accepted validation passed before and after push without
  `--artifact-root`; acceptance source full-read/hash passes were zero.
- The superseded R1 offer remained unaccepted and no R1 artifact was accessed.

## Execution counters and scope

| Counter | Observed |
|---|---:|
| direct path invocations | 1 |
| direct invocation launcher-body entries | 0 |
| Bash recovery launcher-body executions | 1 |
| renderer process executions | 0 |
| promotion executions | 0 |
| scientific calculations | 0 |
| duplicate calculations | 0 |
| eligibility recomputations | 0 |
| compact reference-cell CSV natural reads/digests | 0 |
| predecessor payload reads or hashes | 0 |
| predecessor attestation rehashes | 0 |
| new PNG writes / post-write digests | 0 / 0 |
| validation / held-out accesses | 0 / 0 |
| Roofer / reconstruction / MVS / LiDAR / GS / C3–C5 executions | 0 |

The body performed only its artifact-root directory-form check, Git fetch, and
repository packet/config metadata reads before the authority-parser failure. It did
not open or hash any artifact file.

## Output and visual status

Planned external URI:

`artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_r2_v1/P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R2-v1/`

Observed state: `ABSENT`. Artifact bytes and SHA-256 are `null`. The promoted report
and technical manifest were not generated. No PNG exists, so 2520x1400 decode,
seven-cell original-pixel inspection, and F1–F4 text-containment review are
`NOT_PERFORMED`; no visual PASS is claimed.

## Preserved predecessor results

This technical failure did not alter any roster, count, result, or criterion state:

- C1 G0/G1 remains `51/51` and `51/51`;
- C2 G0/G1 remains `50/51` and `50/51`;
- C2 full/partial/absent remains `46/4/1`;
- G2/G3/G4/`PASS_usable` remains `PENDING`;
- `scientific_verdict` remains `null`.

## Verification

The network-disabled exact-image focused suite ran after the failure:

```text
python -m unittest \
  tests.p2_baselines.c1_c2_qualitative_layout_correction_v1.test_layout_correction \
  tests.p2_baselines.c1_c2_qualitative_layout_correction_v1.test_promotion_contract
```

Result: `Ran 9 tests ... OK`. These tests validate the renderer and promotion units
but do not exercise the launcher's shared AWK authority parser against the R2 packet,
so their PASS does not override the observed launcher preflight failure.

## Closure

This Return and the add-once `200-blocked` receipt preserve the exact accepted
attestation without artifact rehash. A direct-child `300-closed` returns exclusive
writer ownership to Work Host. Any correction requires a new reviewed source/packet
and a new handoff identity that align the authority parser with the packet metadata;
this R2 namespace and receipt chain must not be reopened or rerun.

`scientific_verdict` remains `null`.
