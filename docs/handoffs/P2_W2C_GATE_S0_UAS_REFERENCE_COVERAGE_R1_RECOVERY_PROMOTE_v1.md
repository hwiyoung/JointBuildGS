# P2 Gate S0 UAS reference coverage R1 recovery/promote — ACTIVE

- task_id: `P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-RECOVERY-PROMOTE-v1`
- handoff_id: `P2-W2C-GATE-S0-UAS-REFERENCE-COVERAGE-R1-RECOVERY-PROMOTE-v1`
- status: `APPROVED_FOR_EXECUTION`
- implementation commit: `a24f653a50096afe85e8851585391aaac054a945`
- activation commit: `SELF`
- predecessor closed commit: `c8a13e22f235d3717a3b69275cdc814da768ef28`
- historical accepted/source commit: `da24ba68123ced5b4b95efd558688e92b9c9e086`
- Gate S0 decision: `null`
- scientific_verdict: `null`
- C1–C5 performance: `PROHIBITED`

## Answer first

The R1 scientific calculation is not to be repeated. Its existing compact evidence
reports 72 eligible buildings but only nine independent shared-reference/spatial
groups, so its scope remains `PILOT_ONLY_REFERENCE_SCOPE` and its Gate recommendation
remains `BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE`.

The sole defect is technical: checkpoint records written in the first process include
`digest_method: same_stream_as_add_once_serialization`, while the reload path omitted
that field before comparing the completed ledger. This task may correct that
serializer/reloader mismatch, verify the already existing derived outputs, and
promote them without reopening any scientific source. It may not change the 72/9
result, grouping, split, power, thresholds, or claim scope.

## Immutable historical evidence

The following predecessor records are inputs to this recovery and must remain
byte-identical:

- `control/execution_ledger_v1.json`: 11,268 bytes, SHA-256
  `cdf41594f1c218aa1c60206b9a6c070e5222f00da8149796151b15385f1f6bec`;
- `freeze/technical_summary_v1.json`: 5,434 bytes, SHA-256
  `2ac13fe6edd8227bdfae3f49ae17723fdc057ce58b2ce647dce62c4c445607c7`;
- `freeze/candidate_ledger_v1.csv`: 83,814 bytes, SHA-256
  `7f5759739a473952b4d3826b09c83ec3c2c4e0b68148a51405eb22609cec9b41`;
- `analysis/claim_scope_v1.json`: 9,937 bytes, SHA-256
  `cceac670f9ab27b87cf09ac198fd236d44e8b215f85e13f3f2d11e63f03bb8eb`;
- `reference/patch_summary_v1.csv`: 96,539 bytes, SHA-256
  `8a4379bdc7c58f7470fa37163f5471160601eb0475a86178054e47c5714ea3d0`;
- `reference/patch_association_qa_v1.csv`: 7,078 bytes, SHA-256
  `1dc618a400d795c139b504041321f0ea1676a75f3a3814ae8efeb868351ea93c`.

They are under the exact predecessor namespace
`artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/uas_reference_coverage_r1_v1/P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1/`.
No file in that namespace may be edited, renamed, deleted, regenerated, or used as a
write target.

## Zero-scientific-source recovery contract

The recovery verifier may open and digest only the historical execution ledger,
checkpoint envelopes, attempt/invocation metadata, and the derived outputs referenced
by those checkpoint envelopes. It must fail before promotion unless all paths remain
inside the historical task namespace and every declared byte count and SHA-256
matches.

It must not stat for content validation, open, read, mmap, hash, parse, or regenerate:

- the 3,023,643-byte compact UAS grid;
- the predecessor checkpoint input or predecessor eligibility ledger;
- raw UAS LAZ/XYZ, current images/poses, SfM/MVS/depth/normal/confidence,
  ALS, LoD1/LoD2 geometry, `scene.mvs`, R1 15.7 GB inputs, `Images.zip`, or `OPF.zip`;
- held-out outcomes, C1–C5 performance, Fusion W1, or `R_ext`.

The verifier must not call `capture_exact`, `SourceAttempts.start`, segmentation,
eligibility, association, grouping, splitting, or power functions. Historical source
attempt counts must remain `reference_grid=1` and `eligibility_metadata=1`; the
known-successful/minimum/maximum read-digest accounting must remain 1/1/1 for each
compact input. The new recovery namespace may contain only recovery control metadata.

## Exact bounded implementation

1. Define one canonical checkpoint-record serializer used by both write and reload.
   It must preserve the historical field
   `digest_method: same_stream_as_add_once_serialization`.
2. Add a regression test that writes a checkpoint, constructs a new checkpoint
   manager instance, and proves exact record-list equality. Add a fixture reproducing
   the historical six-record completed-ledger comparison.
3. Implement a recovery-only verifier bound to historical operation commit
   `da24ba68123ced5b4b95efd558688e92b9c9e086`, the historical task/handoff IDs, the
   exact external namespace, and the immutable ledger digest above.
4. Prove the zero-source contract structurally: the recovery entry point has no
   scientific-source arguments or allowed roots, and tests make every forbidden
   source accessor raise if called.
5. Validate the existing six-checkpoint stage sequence and all referenced derived
   output digests. Validate the attempt/invocation accounting without adding an event
   to the historical namespace.
6. Assert, rather than recompute, the frozen result: `U_target=199`,
   `E_paired_candidate=72`, independent groups `9`, held-out buildings/groups `10/2`,
   `PILOT_ONLY_REFERENCE_SCOPE`, and
   `BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE`.
7. Promote byte-identical declared output copies plus one manifest/report into the
   predecessor's previously declared Git promotion paths. The manifest must identify
   this recovery task, the historical operation, every external digest, the
   zero-source-read proof, and `scientific_verdict: null`.
8. The Experiment Host must run verification/promotion once in the accepted immutable
   project image with network disabled and only the new recovery metadata namespace
   plus declared Git promotion paths writable. A second process must take a completed
   recovery fast path without reopening or rehashing scientific sources.

## Allowed new or corrected paths

- this DRAFT and its later activation revision;
- `scripts/input_and_alignment/gate_s0/uas_reference_coverage_r1_v1/run_uas_reference_coverage_r1.py`
  only for the canonical checkpoint-record serializer fix;
- `scripts/input_and_alignment/gate_s0/uas_reference_coverage_r1_recovery_promote_v1/`;
- `configs/input_and_alignment/gate_s0/uas_reference_coverage_r1_recovery_promote_v1/`;
- `tests/input_and_alignment/gate_s0/uas_reference_coverage_r1_recovery_promote_v1/`;
- new external recovery-control namespace
  `artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/uas_reference_coverage_r1_recovery_promote_v1/P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-RECOVERY-PROMOTE-v1/`;
- `artifacts/manifests/gate_s0/uas_reference_coverage_r1_v1/` and
  `docs/research/preregistration/gate_s0/uas_reference_coverage_r1_v1/` only as
  add-once promotion destinations;
- the new handoff receipt directory and the new Return Packet.

All earlier packets, Returns, receipts, research canon, raw/derived predecessor
artifacts, and unrelated repository paths are protected. Promotion must fail if a
declared destination already exists with different bytes or if unrelated worktree
changes are present.

## Acceptance and stopping rule

Technical success requires the exact historical ledger and all derived output digests
to validate, the fresh-process checkpoint-record equality regression to pass, the
historical attempt accounting to remain unchanged, zero scientific-source access, and
byte-identical Git promotion. The Return must use `200-verified.json` followed by a
direct-child `300-closed.json` and return writer ownership.

Any mismatch, source access, regeneration attempt, unexpected dirty path, or changed
scientific count is a `200-blocked.json` event. It must not trigger a retry of the R1
calculation. Even technical success does not authorize P2: the scientific Gate remains
blocked by nine independent groups until a separate Gate decision limits the study to
a pilot or obtains materially more independent evaluation reference.

## Committed-tree review

The exact implementation through
`a24f653a50096afe85e8851585391aaac054a945` passed 45 focused Docker tests covering
the 24 historical R1 tests and 21 recovery/restart tests. Three independent reviews
approved activation after verifying scientific-source isolation, exact acceptance
artifact binding, pending-file quarantine/recovery, clean-state 100 attestation,
partial-promotion retry, exact completed-fast-path identity/destination binding, and
the absence of any scientific recalculation path. The implementation deliberately
excludes volatile worktree-clean state from promoted manifest bytes so a clean first
invocation and dirty partial retry converge on identical add-once outputs.

This activation authorizes only the bounded recovery/promote operation described
above. It does not approve a pilot or any other P2 performance run. Gate S0 decision
and `scientific_verdict` remain `null`.
