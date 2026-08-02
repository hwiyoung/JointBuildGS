# Work-to-Codex Task Packet — P2 C1/C2 qualitative layout correction R5 v1

- handoff_id: `P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-v1`
- task_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-v1`
- status: `APPROVED_FOR_EXECUTION`
- user_approval: `APPROVED_FOR_EXECUTION`
- source_commit: `1794a4593c05eb30da3b0acf96e5dc5f651edaf1`
- run_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-RUN-v1`
- execution_mode: `ELIGIBILITY_LAYOUT_ONLY_CLOSED_ATTESTATION_REUSE`
- project_image_id: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- scientific_verdict: `null`

## Answer first

This final bounded recovery removes the redundant raw `git rev-parse HEAD` call that
stopped closed R4 in the read-only Linux validation container. Exact HEAD ownership
remains enforced before that container and by the canonical handoff validator. The
numeric no-repeat contract remains the sole receipt evidence contract; prose remains
non-authoritative.

R4 closed at commit `0d035500e574053da0a9e568b5ee94811c30f4d8`
before compact CSV inspection, namespace creation, rendering, promotion, or PNG
write. R1–R4 remain immutable. R5 does not recompute C1/C2 or change any scientific
result.

## Exact scope

1. Reuse the original predecessor `300-closed` at commit
   `57205adf16def5382322ee57136b1cd66e9d07bc`: 25 records, 30,432,763 bytes,
   Git-blob SHA-256 `7fc0770501eb3447733b481fe7ccf195064cdb3cb35934744a8db2fca6d0ec64`,
   canonical identity `903b0f744c982f83106099ba280ca98d5fb362cc77867f301a31183a30bb804c`.
   Acceptance performs zero artifact reads or hashes and does not nest R1–R4 reuse.
2. Enforce acceptance from canonical validation plus the unique named numeric `0/0`
   no-repeat test. Do not add a redundant raw Git invocation inside the container.
3. Mount only the exact 3,785,261-byte compact reference-cell CSV. Parse and digest
   it once in the natural rendering stream.
4. Freeze the exact P1/P2/P3/F1/F2/F3/F4 IDs, bboxes, labels, counts, and reasons.
   Do not recompute eligibility or select new examples.
5. Render one add-once 2520x1400 PNG in the fresh R5 namespace with fixed axes and
   exact reason-text containment checks. Digest the PNG once after write.
6. Promotion reads only the new JSON manifest, committed config, and R5 accepted
   receipt. It does not reopen the PNG, predecessor receipt, or scientific inputs.
7. Preserve every prior packet, Return, receipt, report, manifest, and external
   namespace byte-for-byte.

Scientific calculation, eligibility recomputation, metrics, Roofer, reconstruction,
MVS/LiDAR processing, GS, C3/C4/C5, validation and held-out accesses are all zero.
C1 G0/G1 remains 51/51; C2 G0/G1 remains 50/51; C2 full/partial/absent remains
46/4/1; G2/G3/G4/PASS_usable remains pending; `scientific_verdict` remains `null`.

## Required outputs

- external namespace:
  `artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_r5_v1/P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-v1/`
- report:
  `docs/experiments/p2/c1_c2_qualitative_layout_correction_r5_v1/C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R5_v1.md`
- technical manifest:
  `artifacts/manifests/p2_baselines/c1_c2_qualitative_layout_correction_r5_v1/technical_result_manifest_v1.json`
- Return:
  `docs/handoffs/returns/P2_C2W_C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R5_RETURN_v1.md`
- receipts:
  `artifacts/manifests/handoffs/P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R5-v1/`

## Done when

The activated packet and launcher mode pass the committed tests; the accepted receipt
passes canonical and numeric no-repeat validation; the single direct launcher succeeds;
the PNG decodes at 2520x1400; automated containment and original-pixel inspection pass;
Return and 200/300 close the R5 chain; writer ownership returns to Work Host; and
`scientific_verdict` remains `null`.
