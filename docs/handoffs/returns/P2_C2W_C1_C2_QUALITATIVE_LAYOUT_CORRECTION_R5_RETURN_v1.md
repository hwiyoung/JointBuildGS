# Codex-to-Work Return — P2 C1/C2 qualitative layout correction R5 v1

## Return metadata

- handoff_id: `P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-v1`
- task_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-v1`
- source implementation commit: `1794a4593c05eb30da3b0acf96e5dc5f651edaf1`
- activation commit: `695f450d7963b8ee0e523f5850fa8128400a380e`
- offered commit: `67922c2d688342a5f245b1a30ead757a03587575`
- accepted commit: `11e6deb17839f1bebb8885af6ae891efb60df807`
- Return / 200-verified commit: `SELF`
- 300-closed commit: `PENDING_DIRECT_CHILD_EVENT`
- run_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-RUN-v1`
- project image: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- completed_at: `2026-08-02T19:48:10+09:00`
- proposed technical status: `COMPLETE_LAYOUT_CORRECTION`
- scientific_verdict: `null`

## Answer first

R5 completed the bounded layout-only correction with one direct launcher invocation.
The new PNG passed automated exact-text containment and original-pixel inspection at
2520x1400. All seven P1/P2/P3/F1/F2/F3/F4 panels and labels are visible, and the
complete F1-F4 rejection-reason text is visible and unclipped.

No C1/C2 reconstruction, association, eligibility, metric, or scientific result was
recomputed. Validation and held-out payloads, Roofer, MVS, LiDAR, GS, and C3-C5 were
not accessed or executed. This is technical closure evidence only;
`scientific_verdict` remains `null`.

## Immutable acceptance and bounded execution

- The original predecessor `300-closed` at
  `57205adf16def5382322ee57136b1cd66e9d07bc` was reused directly, without
  R1-R4 attestation nesting.
- Its Git-blob SHA-256 is
  `7fc0770501eb3447733b481fe7ccf195064cdb3cb35934744a8db2fca6d0ec64`;
  its 25 artifact records total 30,432,763 bytes and have canonical identity
  `903b0f744c982f83106099ba280ca98d5fb362cc77867f301a31183a30bb804c`.
- Acceptance performed zero external artifact reads or hashes and the committed
  `100-accepted` carried exactly the named numeric `0/0` no-repeat test.
- The launcher was invoked exactly once and was not rerun.

## Execution counters

| Counter | Observed |
|---|---:|
| direct launcher invocations | 1 |
| compact reference-cell CSV natural reads / digests | 1 / 1 |
| compact CSV bytes / rows | 3,785,261 / 20,520 |
| fresh R5 namespace creations | 1 |
| renderer process executions | 1 |
| promotion process executions | 1 |
| fresh PNG writes / post-write digests | 1 / 1 |
| predecessor external artifact reads / hashes | 0 / 0 |
| old R1-R4 artifact or namespace rehashes | 0 |
| scientific calculations / eligibility recomputations | 0 / 0 |
| validation / held-out payload accesses | 0 / 0 |
| Roofer / reconstruction / MVS / LiDAR / GS / C3-C5 executions | 0 |

The promoted external URI is:

`artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_r5_v1/P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-v1/`

The single new figure is
`eligibility_199_to_72_fixed_cells_layout_corrected_v1.png`, 245,765 bytes, with
the renderer's sole post-write SHA-256
`1a1540f380f7fbc1a950e806b879c01ad744cc8cf7e5bcef42cb761923938022`.
No closure-time PNG rehash was performed.

## Original-pixel inspection

| Label | Stable ID | Status | Views / MVS / C4 / reference cells | Full displayed reason |
|---|---|---|---:|---|
| P1 | `DEBY_LOD2_4959324` | ELIGIBLE | 228 / 97 / 87 / 5 | `PASS_ALL_INPUT_SUPPORT_RULES` |
| P2 | `DEBY_LOD2_4959793` | ELIGIBLE | 241 / 282 / 193 / 97 | `PASS_ALL_INPUT_SUPPORT_RULES` |
| P3 | `DEBY_LOD2_4959460` | ELIGIBLE | 399 / 8842 / 6740 / 3543 | `PASS_ALL_INPUT_SUPPORT_RULES` |
| F1 | `DEBY_LOD2_4907184` | EXCLUDED | 186 / 521 / 451 / 3 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT` |
| F2 | `DEBY_LOD2_4907034` | EXCLUDED | 61 / 0 / 574 / 0 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT; INSUFFICIENT_MVS_SUPPORT` |
| F3 | `DEBY_LOD2_4908166` | EXCLUDED | 85 / 40 / 3 / 0 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT; INSUFFICIENT_C4_SUPPORT` |
| F4 | `DEBY_LOD2_4908164` | EXCLUDED | 63 / 0 / 0 / 0 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT; INSUFFICIENT_MVS_SUPPORT; INSUFFICIENT_C4_SUPPORT` |

The image tool was used at original pixels. Panel frames, axes, titles, eligibility
labels, counts, and every reason line above remain within the image bounds.

## Verification

The immutable, network-disabled project image ran the focused predecessor and R5
successor suite: 20 passed, 0 failed. The committed `100-accepted` canonical
validator passed before execution. The committed `200-verified` is validated only
after its push, with no artifact-root mount and no rehash of the PNG or predecessor
artifacts.

## Preserved scientific state

- C1 G0: `51/51`; C1 G1: `51/51`.
- C2 G0: `50/51`; C2 G1: `50/51`.
- C2 full/partial/absent counts remain `46/4/1`
  (`46/50`, `4/50`, `1/51` in the promoted report).
- G2/G3/G4/`PASS_usable`: `PENDING`.
- `scientific_verdict`: `null`.

A separate direct-child `300-closed` returns exclusive writer ownership to Work Host
without reopening or hashing any source or result payload.
