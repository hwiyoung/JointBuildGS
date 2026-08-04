# P2 C1/C2/C3 U_target=199 combined closure v1

- task_id: `P2-C1-C2-C3-UTARGET199-CLOSURE-v1`
- handoff_id: `P2-W2C-C1-C2-C3-UTARGET199-CLOSURE-v1`
- status: `APPROVED_FOR_VERIFICATION_ONLY`
- source_commit: `84dc2715d74882618ab314b685234974d2bf11e5`
- scientific_verdict: `null`

## Closure scope

This verification-only closure binds the already completed C1/C2 sample, exact C3
checkpoint pair, and complete C3 all-199 postprocess recovery.  It performs no renderer,
training, Roofer, G2, or metric computation.

Required verification:

1. C1/C2: 3 cases, 60 panels, display methods `C1_L_upper` and `C2_MVS`, exact 6-row
   quantitative source, 60 projection receipts and positive required-panel visibility.
2. C3 training: common seed 0 with 371,808 sparse + 103,546 neutral dense initial
   representatives, exact 937 views, two 30,000-step checkpoint hashes.
3. C3 postprocess: 199 buildings, 398 result rows, 25 Roofer terminal receipts, 8 actual
   gsplat panels, 199 case sheets, qualitative HTML, native center PLY and surfel mesh for
   both conditions.
4. Original-resolution visual review of `DEBY_LOD2_4907177`, `DEBY_LOD2_4906975`, and
   `DEBY_LOD2_108580336` for both the C1/C2 and C3 sheets.
5. Execution accounting and interpretation boundary remain explicit: the C1/C2 run
   invoked Roofer/G2/GS/metric recomputation zero times; C3 invoked GS training twice and
   unique Roofer 25 times; postprocess recovery reran Roofer/metrics zero times; C4/C5
   access stayed zero.

## Preserved operational incidents

- The first C3 postprocess stopped only at the qualitative gsplat background-channel
  assertion after geometry, Roofer and 398 rows completed.  Its namespace is preserved.
- The immutable C3-2 v1 `300-closed` and later v2 `200-verified` attempts are not valid
  successful closure receipts.  Their validators rejected technical-state/direct-lineage
  conditions.  They remain failure evidence and are not rewritten.
- Neither incident changes checkpoint or result artifact identity.  This fresh combined
  closure starts after all result commits so its 200/300 chain can be direct and bounded.

## Interpretation boundary

C3-1 associates 16/199 buildings and C3-2 associates 18/199; each has 3 one-to-one
associations and both have building G0 0/199.  Official G3/G4/PASS and continuous building
accuracy therefore remain `null`.  This is non-confirmatory technical evidence, not a
scientific approval, method ranking, or population/generalization verdict.

Serialized-main receipts in this operator workflow are the agreed role/ownership record;
no physical Work Host visit is required.
