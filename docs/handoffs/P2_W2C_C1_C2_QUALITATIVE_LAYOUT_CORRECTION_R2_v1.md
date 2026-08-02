# Work-to-Codex Task Packet — P2 C1/C2 qualitative layout correction R2 v1

- handoff_id: `P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R2-v1`
- task_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R2-v1`
- status: `ACTIVATED_FOR_EXECUTION`
- explicit_user_authorization: `APPROVED_FOR_EXECUTION`
- source_commit: `9ac8e85ffa116d5807e881a95086e3dce3e571e2`
- run_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R2-RUN-v1`
- execution_mode: `ELIGIBILITY_LAYOUT_ONLY_CLOSED_ATTESTATION_REUSE`
- project_image_id: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- scientific_verdict: `null`

## Answer first

This bounded task makes the already-computed C1/C2 backfill understandable by fixing
only the clipped reason text in the seven-cell `199 -> 72` eligibility figure. It
does not rerun C1/C2, alter any count, or open C3. The 51 per-building qualitative
sheets, stage counts, and final-result fields remain the predecessor's outputs.

The R1 offer at commit `4fb87c4753a5338e94a7a37993fde7b8ba02db7f`
was superseded before acceptance, pull, artifact access, or writer transfer. Its
predecessor receipt digest had been calculated from a Windows CRLF checkout. R2 binds
the immutable Git blob / Linux checkout bytes instead:
`7fc0770501eb3447733b481fe7ccf195064cdb3cb35934744a8db2fca6d0ec64`.
The R1 packet and `000-offered` receipt remain immutable historical evidence.

## Exact scope

1. Inherit the exact 25-record, 30,432,763-byte artifact object from predecessor
   `300-closed` commit `57205adf16def5382322ee57136b1cd66e9d07bc` using
   `closed_attestation_reuse`; acceptance performs zero artifact reads or hashes.
2. At runtime mount only the exact 3,785,261-byte compact reference-cell CSV and
   parse plus digest it once in the natural rendering stream.
3. Freeze the exact P1/P2/P3/F1/F2/F3/F4 IDs, bboxes, candidate labels,
   cell/view/MVS/C4 counts, and reasons. Do not recompute eligibility or examples.
4. Render one add-once 2520x1400 PNG in the fresh R2 namespace, with a fixed grid,
   separate text axes, exact semicolon-preserving reason text, and post-draw text and
   canvas containment checks. Do not use `constrained_layout`, `tight_layout`, or
   `bbox_inches=tight`.
5. Digest the new PNG once after write. Promotion reads only the new JSON manifest,
   committed config, and R2 accepted receipt; it does not reopen the PNG or any
   predecessor scientific input.
6. Preserve every prior packet, Return, receipt, report, table, manifest, and external
   namespace byte-for-byte.

Scientific calculation, eligibility recomputation, metrics, Roofer, reconstruction,
MVS/LiDAR processing, GS, C3/C4/C5, validation and held-out accesses are all zero.
C1 G0/G1 remains 51/51; C2 G0/G1 remains 50/51; C2 full/partial/absent remains
46/4/1; G2/G3/G4/PASS_usable remains pending; `scientific_verdict` remains `null`.

## Required outputs

- new external namespace:
  `artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_r2_v1/P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R2-v1/`
- report:
  `docs/experiments/p2/c1_c2_qualitative_layout_correction_r2_v1/C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R2_v1.md`
- technical manifest:
  `artifacts/manifests/p2_baselines/c1_c2_qualitative_layout_correction_r2_v1/technical_result_manifest_v1.json`
- Return:
  `docs/handoffs/returns/P2_C2W_C1_C2_QUALITATIVE_LAYOUT_CORRECTION_R2_RETURN_v1.md`
- receipts:
  `artifacts/manifests/handoffs/P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R2-v1/`

## Done when

Container tests pass; the one corrected PNG decodes at 2520x1400; automated text
containment and independent original-pixel inspection pass; the Return records exact
commits and zero-repeat counters; `200-verified` and direct-child `300-closed` return
writer ownership to Work Host; and `scientific_verdict` remains `null`.
