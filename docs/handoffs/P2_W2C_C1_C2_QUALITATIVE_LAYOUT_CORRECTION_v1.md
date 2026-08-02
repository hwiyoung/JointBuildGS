# Work-to-Codex Task Packet — P2 C1/C2 qualitative layout correction v1

- handoff_id: `P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-v1`
- task_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-v1`
- status: `ACTIVATED_FOR_EXECUTION`
- explicit_user_authorization: `APPROVED_FOR_EXECUTION`
- source_commit: `93cbbbdc067eb2a78b32c802162d233949c86bd3`
- run_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-RUN-v1`
- execution_mode: `ELIGIBILITY_LAYOUT_ONLY_CLOSED_ATTESTATION_REUSE`
- project_image_id: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- scientific_verdict: `null`

## Answer first

The preceding C1/C2 qualitative backfill is numerically and scientifically unchanged,
but it closed blocked because the exact F1–F4 exclusion reasons escaped the seven-cell
`199 -> 72` figure. This successor fixes only that display defect. It does not rerun
the 51 building sheets, recompute C1/C2, or open C3.

## Exact scope

1. Inherit the exact 25-record, 30,432,763-byte artifact object from predecessor
   `300-closed` commit `57205adf16def5382322ee57136b1cd66e9d07bc` using
   `closed_attestation_reuse`; acceptance performs zero artifact reads or hashes.
   The accepted receipt must contain exactly one test named
   `acceptance artifact source full-read or hash passes` with `passed=0, failed=0`,
   and its 25 ordered URI/bytes/SHA identities must equal the predecessor receipt.
2. At runtime mount only the exact 3,785,261-byte compact reference-cell CSV. Parse
   and digest it once in the natural render stream. Do not mount R1/raw UAS,
   `Images.zip`, `OPF.zip`, R3, C1/C2 geometry, validation, or held-out payloads.
3. Freeze the exact P1/P2/P3/F1/F2/F3/F4 IDs, bboxes, candidate labels, cell/view/MVS/C4
   counts, and reasons. Do not recompute eligibility or select examples.
4. Render one corrected add-once PNG in a new external namespace using a fixed 2x4
   grid with a separate text area per example. Semicolon-separated reason tokens may
   be line-broken only; concatenating the displayed lines must reproduce the exact
   stored reason.
5. Fail closed unless every required annotation lies inside its allotted axes and all
   figure decorations lie inside the output canvas after the final Agg draw. Do not
   use adaptive per-example layout, `constrained_layout`, `tight_layout`, or
   `bbox_inches=tight`.
6. Digest the new PNG once after write. Promotion may read only the new JSON manifest,
   committed task config and accepted receipt; it must not reopen the PNG, predecessor
   receipt, eligibility CSV/bbox ledger, compact CSV, or another scientific input.
7. Preserve all prior packet/Return/receipt/report/table/manifest files and the prior
   blocked external namespace byte-for-byte.

Scientific calculation, eligibility recomputation, metrics, Roofer, reconstruction,
MVS/LiDAR processing, GS, C3/C4/C5, validation and held-out accesses are all zero.
C1 G0/G1 remains 51/51; C2 G0/G1 remains 50/51; C2 full/partial/absent remains
46/4/1; G2/G3/G4/PASS_usable remains pending; `scientific_verdict` remains `null`.

## Required outputs

- new external namespace:
  `artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_v1/P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-v1/`
- report:
  `docs/experiments/p2/c1_c2_qualitative_layout_correction_v1/C1_C2_QUALITATIVE_LAYOUT_CORRECTION_v1.md`
- technical manifest:
  `artifacts/manifests/p2_baselines/c1_c2_qualitative_layout_correction_v1/technical_result_manifest_v1.json`
- Return:
  `docs/handoffs/returns/P2_C2W_C1_C2_QUALITATIVE_LAYOUT_CORRECTION_RETURN_v1.md`
- receipts:
  `artifacts/manifests/handoffs/P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-v1/`

## Done when

Container tests pass; the one corrected PNG decodes at 2520x1400; automated text
containment and independent original-pixel inspection pass; the Return records exact
commits and zero-repeat counters; `200-verified` and direct-child `300-closed` return
writer ownership to Work Host; and `scientific_verdict` remains `null`.
