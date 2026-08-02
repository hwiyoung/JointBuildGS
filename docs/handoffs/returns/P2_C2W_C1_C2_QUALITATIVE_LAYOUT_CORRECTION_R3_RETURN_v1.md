# Codex-to-Work Return — P2 C1/C2 qualitative layout correction R3 v1

## Return metadata

- handoff_id: `P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R3-v1`
- task_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R3-v1`
- source implementation commit: `968fdfd13e26a60dcd729dff3206b65030476358`
- activation commit: `1e865d6d81aa84e431ce0759097b9e168f7b45c9`
- offered commit: `003a9face23c3d1bf822ef330ebc3662e080770e`
- accepted commit: `965f857ce6112530776715335ec959dcfe54a3b8`
- Return / 200-blocked commit: `SELF`
- 300-closed commit: `PENDING_DIRECT_CHILD_EVENT`
- run_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R3-RUN-v1`
- project image: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- completed_at: `2026-08-02T19:20:31+09:00`
- proposed technical status: `BLOCKED_ACCEPTED_RECEIPT_COMMAND_LITERAL_CONTRACT`
- scientific_verdict: `null`

## Answer first

R3 did not reach artifact-file inspection or rendering. The exactly requested direct
launcher invocation ran once, fetched `origin/main`, proved the clean accepted
HEAD/config/packet tuple, passed the canonical `100-accepted` validator, and then
stopped with exit 1 at the protected embedded accepted-receipt contract.

The exact failed assertion requires one `verification.commands` string in the
immutable R3 `100-accepted` receipt to contain all four uppercase literals after
normalization:

```text
WITHOUT --ARTIFACT-ROOT
ZERO
READ
HASH
```

The accepted receipt contains `without --artifact-root` but does not contain the
other three literals in that command. Python therefore raised `AssertionError` at
`<string>` line 31. Because the launcher uses `set -e`, it stopped before the compact
CSV existence check, fresh R3 namespace creation, renderer, promotion, or PNG write.
The launcher was not rerun and the immutable `100-accepted` receipt was not edited.

## Ownership and immutable acceptance

- The pull-precheck proved offered commit `003a9face23c3d1bf822ef330ebc3662e080770e`,
  activation commit `1e865d6d81aa84e431ce0759097b9e168f7b45c9`, and source commit
  `968fdfd13e26a60dcd729dff3206b65030476358` before fast-forward.
- The original predecessor `300-closed` was read from immutable commit
  `57205adf16def5382322ee57136b1cd66e9d07bc`. Its Git-blob SHA-256 is
  `7fc0770501eb3447733b481fe7ccf195064cdb3cb35934744a8db2fca6d0ec64`.
- The directly reused artifact object contains 25 records and 30,432,763 bytes with
  canonical identity
  `903b0f744c982f83106099ba280ca98d5fb362cc77867f301a31183a30bb804c`.
- Add-once accepted commit `965f857ce6112530776715335ec959dcfe54a3b8`
  points directly to that original predecessor; it does not nest R1 or R2.
- Acceptance and launcher preflight used only Git-owned receipt metadata. No one of
  the 25 predecessor artifacts was opened or hashed.

## Execution counters and scope

| Counter | Observed |
|---|---:|
| direct launcher invocations | 1 |
| launcher-body entries | 1 |
| canonical accepted-receipt validator passes inside launcher | 1 |
| embedded accepted-receipt command-contract failures | 1 |
| compact reference-cell CSV natural reads / digests | 0 / 0 |
| predecessor artifact reads / hashes | 0 / 0 |
| fresh R3 namespace creations | 0 |
| renderer process executions | 0 |
| promotion executions | 0 |
| new PNG writes / post-write digests | 0 / 0 |
| scientific calculations / eligibility recomputations | 0 / 0 |
| validation / held-out accesses | 0 / 0 |
| Roofer / reconstruction / MVS / LiDAR / GS / C3–C5 executions | 0 |

The host launcher checked only that the artifact root itself was an existing absolute
non-symlink directory. Its embedded acceptance check read and hashed the Git-tracked
original predecessor receipt, not an external artifact payload. It terminated before
shell lines that inspect the compact CSV path or create the output namespace.

## Output and visual status

Planned external URI:

`artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_r3_v1/P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R3-v1/`

Observed execution state: `NOT_CREATED_BY_R3`. No report, technical manifest, or PNG
was promoted. Consequently 2520x1400 decoding, original-pixel P1/P2/P3/F1/F2/F3/F4
inspection, and F1–F4 rejection-reason containment review are `NOT_PERFORMED`; no
visual PASS is claimed.

## Preserved predecessor results

This pre-artifact technical failure did not alter any C1/C2 number or criterion state:

- C1 G0/G1 remains `51/51` and `51/51`;
- C2 G0/G1 remains `50/51` and `50/51`;
- C2 full/partial/absent remains `46/4/1`;
- G2/G3/G4/`PASS_usable` remains `PENDING`;
- `scientific_verdict` remains `null`.

## Verification and closure

The network-disabled canonical validator passed the committed `100-accepted` receipt
before the launcher. The same validator passed again inside the launcher before the
literal command-contract assertion. Focused renderer/promotion tests were not run
because the packet schedules them after launcher success and no success occurred.

This Return and add-once `200-blocked` receipt preserve the direct original-predecessor
attestation without artifact access. A separate direct-child `300-closed` returns
exclusive writer ownership to Work Host. R1 and R2 receipt chains and namespaces remain
closed and untouched. Any correction requires a new reviewed handoff identity; this R3
body must not be rerun or reopened.

`scientific_verdict` remains `null`.
