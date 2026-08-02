# Work-to-Experiment Task Packet — C1/C2 G2 + C3 first-wave recovery R1 v1

- handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R1-v1`
- task_id: `P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R1-v1`
- status: `DRAFT_NOT_AUTHORIZED`
- parent_handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-v1`
- source_commit: `SELF`
- scientific_verdict: `null`

## Purpose

Recover only the cross-host preflight defects recorded by the closed parent task.
No scientific input was read and no optimizer update ran in that task. This recovery
therefore resumes the already-approved work without changing its cohort, recipe,
criteria, or data roles.

## Frozen scientific scope

- common source: 962 images / 937 exact image-pose pairs / 25 excluded images
- population: 199 total, 72 independently evaluable, 127 excluded
- common C1/C2/C3 comparison cohort: development 51 only
- validation 11 and held-out 10: unopened and prohibited
- C3 scene: one 937-view whole-scene model, seed 0, 30,000 updates
- initialization: all 371,808 SfM points plus the finest 0.10/0.20/0.40 m
  center-nearest dense candidate not exceeding 3,000,000 points
- sparse-only and full 43,942,554-point dense direct initialization: prohibited
- semantic and depth losses, gravity, Stage-3 role, leakage barriers, and output
  contracts: unchanged from the parent packet

## Recovery-only source changes

1. Bind Git-owned text to canonical committed LF bytes while accepting a Windows
   CRLF checkout of those same bytes; reject lone CR and all content drift.
2. Trust only the exact resolved read-only repository path for producer Git checks;
   do not use a global wildcard safe-directory.
3. Run Linux-container regressions against actual committed blobs and a deliberately
   dubious-ownership repository fixture before handoff.

## Execution

After an accepted receipt, reuse the parent's still-empty external namespace and run
only the stages that stopped before input access:

1. C1/C2 G2 and continuous G3/G4 diagnostics on the same development 51.
2. The compact 199→72→51 quantitative explanation and fixed qualitative pass/fail
   examples.
3. One natural read of the dense source to count all three spacings, bind its digest,
   and write the selected candidate.
4. Exact-937 semantic manifest/assets and resumable inference.
5. Exact-937 C3 training after all RGB/depth/semantic/initialization gates pass.

The parent packet's duplicate-work contract remains binding: no R1, `Images.zip`, or
`OPF.zip` full rehash; no C1/C2 reconstruction or Roofer rerun; no validation,
held-out, C4, C5, Fusion W1, or `R_ext` access.

## Outputs and completion

Use the parent's required outputs and external namespace:
`artifact://JointBuildGS/phase-payloads/p2/c1_c2_g2_c3_first_wave_v1/P2-C1-C2-G2-C3-FIRST-WAVE-v1/`.
The namespace was confirmed empty after the preflight failure. Add new recovery
receipts and a new recovery Return only; never modify the parent's packet, Return,
or receipts.

The task completes when the authorized stages finish once or fail visibly, exact
runtime/commit identities and read counters are recorded, writer ownership returns
to Work Host through a direct-child `300-closed`, and `scientific_verdict` remains
`null`.
