# Work-to-Codex Task Packet — P2 C1/C2 qualitative layout correction R3 v1

- handoff_id: `P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R3-v1`
- task_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R3-v1`
- status: `DRAFT`
- user_approval: `PENDING_EXACT_SOURCE_COMMIT`
- source_commit: `PENDING_EXACT_SOURCE_COMMIT`
- run_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R3-RUN-v1`
- execution_mode: `ELIGIBILITY_LAYOUT_ONLY_CLOSED_ATTESTATION_REUSE`
- project_image_id: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- scientific_verdict: `null`

## Answer first

This recovery fixes the two pre-render execution-contract defects observed in closed
R2 and then performs the same one-figure display correction. The launcher is Git mode
`100755`, and the activated packet must contain the two exact literals consumed by
the committed authority parser. An automated test feeds the actual packet contract
to that parser and checks the launcher Git mode.

R1 and R2 remain immutable. R2 closed at commit
`53956789281ddc99030cf511ab6cc08db3de15e9` before artifact access, namespace
creation, rendering, promotion, or PNG write. R3 does not recompute C1/C2 or change
any scientific result.

## Exact scope

1. Reuse the original predecessor `300-closed` at commit
   `57205adf16def5382322ee57136b1cd66e9d07bc`: 25 records, 30,432,763 bytes,
   Git-blob SHA-256 `7fc0770501eb3447733b481fe7ccf195064cdb3cb35934744a8db2fca6d0ec64`,
   canonical identity `903b0f744c982f83106099ba280ca98d5fb362cc77867f301a31183a30bb804c`.
   Acceptance performs zero artifact reads or hashes and does not nest R2 reuse.
2. Mount only the exact 3,785,261-byte compact reference-cell CSV. Parse and digest
   it once in the natural rendering stream.
3. Freeze the exact P1/P2/P3/F1/F2/F3/F4 IDs, bboxes, labels, counts, and reasons.
   Do not recompute eligibility or select new examples.
4. Render one add-once 2520x1400 PNG in the fresh R3 namespace with fixed axes and
   exact reason-text containment checks. Digest the PNG once after write.
5. Promotion reads only the new JSON manifest, committed config, and R3 accepted
   receipt. It does not reopen the PNG, predecessor receipt, or scientific inputs.
6. Preserve every prior packet, Return, receipt, report, manifest, and external
   namespace byte-for-byte.

Scientific calculation, eligibility recomputation, metrics, Roofer, reconstruction,
MVS/LiDAR processing, GS, C3/C4/C5, validation and held-out accesses are all zero.
C1 G0/G1 remains 51/51; C2 G0/G1 remains 50/51; C2 full/partial/absent remains
46/4/1; G2/G3/G4/PASS_usable remains pending; `scientific_verdict` remains `null`.

## Required outputs

- external namespace:
  `artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_r3_v1/P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R3-v1/`
- report:
  `docs/experiments/p2/c1_c2_qualitative_layout_correction_r3_v1/C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R3_v1.md`
- technical manifest:
  `artifacts/manifests/p2_baselines/c1_c2_qualitative_layout_correction_r3_v1/technical_result_manifest_v1.json`
- Return:
  `docs/handoffs/returns/P2_C2W_C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R3_RETURN_v1.md`
- receipts:
  `artifacts/manifests/handoffs/P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R3-v1/`

## Done when

The actual activated packet passes the committed authority parser; the direct
launcher invocation succeeds; the PNG decodes at 2520x1400; automated containment
and actual original-pixel inspection pass; Return and 200/300 close the fresh R3
chain; writer ownership returns to Work Host; and `scientific_verdict` remains null.
