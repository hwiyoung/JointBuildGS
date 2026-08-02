# Work-to-Experiment Task Packet — C1/C2 G2 + C3 first wave v1

- handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-v1`
- task_id: `P2-C1-C2-G2-C3-FIRST-WAVE-v1`
- status: `DRAFT_NOT_EXECUTION_AUTHORITY`
- user_approval: `PENDING_PACKET_ACTIVATION`
- source_commit: `PENDING_SOURCE_COMMIT`
- run_id: `P2-C1-C2-G2-C3-FIRST-WAVE-RUN-v1`
- scientific_verdict: `null`

## Answer first

This is one bounded execution task, not another research-definition exercise. It does
three things: closes the actual val3dity G2 measurement for the already sealed C1/C2
development outputs; chooses the C3 dense initialization from 0.10/0.20/0.40 m
candidates in one natural read; and runs one exact-937-view C3 training job with
image-derived depth and image-only semantic supervision.

The TUM2TWIN research roster remains exactly 199 total, 72 eligible, and 127 excluded.
The number 127 is the excluded count, not a C3 cohort. C1, C2, and C3 are compared on
the identical 51-building development roster. The 11 validation and 10 held-out IDs
remain unopened in this task.

## Frozen inputs and decisions

- common current source: `B_CURRENT_CANDIDATE_c205892c390997b5`
- source membership: 962 images / 937 exact image-pose pairs / 25 excluded images
- C3 scene mode: one whole-scene model over all 937 views
- comparison roster: frozen development 51 only
- SfM initialization: all 371,808 sparse points retained
- dense source: exact 659,138,498-byte / 43,942,554-point `dim_dense.ply`
- dense selection: count 0.10, 0.20, and 0.40 m center-nearest voxel candidates in
  one source stream and select the finest candidate not exceeding 3,000,000 points
- forbidden initialization: sparse-only and full 43,942,554-point dense direct init
- gravity: reuse the frozen terrain-MVS-normal estimate; do not hardcode a new axis
- semantic source: exact 937 RGB images only; no pose crop, footprint, building ID,
  UAS, ALS, LoD1, or LoD2 input
- semantic labels: unknown=0/ignore, roof=1, facade-or-wall=2,
  ground-road-or-pavement=3
- C3 training: one seed (`0`), one 30,000-update job, exact committed config
- external MVS normal-map loss: off; intrinsic rendered-normal consistency: on
- validation, held-out, Fusion W1, C4, C5, LoD1, LoD2, ALS, UAS and `R_ext`: prohibited

## Exact execution stages

1. Verify the accepted two-host receipt and exact clean source commit.
2. Reuse the closed R3 C1/C2 artifact attestation. Read the six sealed C2
   CityJSONSeq streams once each and run pinned val3dity 2.6.0. Emit C1/C2 G2 plus
   continuous G3/G4 diagnostic rows; keep `PASS_usable=null`.
3. Build the exact-937 semantic image manifest from the Git-owned R1 per-image ledger
   without reopening or rehashing `Images.zip`.
4. Verify the C3 GroundedSAM runtime and exact source/weight/BERT assets. Infer each
   image once; completed image receipts are resumable and never reinferred.
5. Read `dim_dense.ply` once. In that same stream compute its digest, exact source
   count, all three voxel candidate counts, and the selected output. Do not add a
   second inspection or hash pass.
6. Before the first optimizer update, require exact 937/937 RGB, depth maps, and
   semantic masks; exact view-role membership; initial Gaussian count within the
   4,000,000 cap; and clean source HEAD.
7. Run C3 seed 0 through 30,000 completed optimizer updates with checkpoints at
   5k/10k/20k/30k. No outcome-based retry or recipe change is allowed.

## Duplicate-work and leakage contract

- R1 15.7 GB input, `Images.zip`, and `OPF.zip`: zero new full hashes
- prior R3 C1/C2 reconstruction and Roofer: zero reruns
- dense source: one natural full read total
- each exact RGB: one natural verification/inference read; completed images resume
  without inference
- validation and held-out reference reads: zero
- C1 self-reference G3/G4/PASS: null
- C2 G3/G4: diagnostic-only in this task
- no GT or evaluation reference may alter C3 input, crop, initialization, loss,
  checkpoint selection, stopping, or retry

## Required outputs

- C1/C2 G2 receipt and 102-row development diagnostic table
- 199→72 compact quantitative table and fixed qualitative pass/fail examples
- exact-937 semantic input manifest, per-image completion receipts, masks, and final
  output manifest
- dense candidate counts, selected spacing/count, exact one-read receipt, and selected
  PLY
- C3 effective config, exact view/depth/semantic inventory audit, 5k/10k/20k/30k
  full-state checkpoints, training logs, and final technical receipt
- Return Packet and 200-verified / direct-child 300-closed receipts

The external namespace is add-once:
`artifact://JointBuildGS/phase-payloads/p2/c1_c2_g2_c3_first_wave_v1/P2-C1-C2-G2-C3-FIRST-WAVE-v1/`.

## Explicit non-goals and next task

This task does not invent final G3/G4 thresholds and does not claim final
`PASS_usable`. Once the C3 checkpoint is sealed, the next bounded task is the common
footprint-free Stage-3 read-out and C1/C2/C3 quantitative/qualitative comparison on
the same development 51 buildings. That task may be drafted from the sealed C3
artifact without changing the model or opening validation/held-out data.

## Done when

All required stages either complete once or fail visibly; every result is bound to
the exact commit and runtime; no prohibited data are read; Return and receipt chain
close; writer ownership returns to Work Host; and `scientific_verdict` remains
`null`.
