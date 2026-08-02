# Work-to-Experiment Task Packet — C1/C2 qualitative and evaluator backfill v1

## Handoff metadata

- handoff_id: `P2-W2C-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1`
- task_id: `P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1`
- phase: `P2_GATE_S0_POST_HOC_DEVELOPMENT_EVIDENCE`
- direction: `Work Host -> Experiment Host`
- status: `DRAFT`
- packet_version: `v1`
- source_commit: `6c4d2491154cb88659809aef245d87c5d6d651ed`
- offered_receipt_commit: `TO_BE_CREATED_ONLY_AFTER_REVIEW_AND_EXPLICIT_ACTIVATION`
- target_branch: `main`
- research_charter_version: `C1C5_CANON_v2`
- result_contract_version: `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
- decision_log_through: `DEC-P1-013`
- supersedes: `none`
- user_approval: `NOT_GRANTED_FOR_EXECUTION`
- scientific_verdict: `null`

This DRAFT records the next bounded task. It is not an execution request. Activation
requires an exact reviewed implementation/config commit, an immutable offered receipt,
and a separate explicit human authorization tuple.

## Goal

Add the missing **post-hoc, fixed-rule qualitative and evaluator-status supplement**
to the already sealed C1/C2 development pilot without repeating reconstruction,
Roofer, scoring, eligibility calculation, or source verification.

The task has four outputs with a deliberately narrow meaning:

1. deterministic geometry-only views of the seven already sealed C1/C2 operation
   outputs, reused by all development rows that share an operation;
2. actual `199 -> 72` eligibility panels for the already fixed examples
   `P1/P2/P3/F1/F2/F3/F4`, drawn only from the artifact-bound compact reference-cell
   rows plus Git-bound bounding boxes, counts, and reason codes;
3. a stage funnel that distinguishes existing G0/provisional-G1 evidence from the
   unavailable G2/G3/G4/final-acceptance stages; and
4. an additive erratum recording the manifest-bound C2 coverage counts as
   `46 full / 4 partial / 1 absent`.

This work improves legibility and auditability. It does not change any metric or make
a scientific success claim.

## Scientific context and interpretation lock

- The frozen development denominator is 51 buildings. Validation 11 and held-out 10
  remain unopened.
- C1 is a self-reference upper baseline and is not an independent-reference accuracy
  comparator. Independent UAS remains score-only.
- The R4 102-row result surface is final for this supplement: 51 C1 rows and 51 C2
  rows. C1 has 51 generated/provisional-G1 rows; C2 has 50. C2 building
  `DEBY_LOD2_4907183` remains absent because no frozen MVS component is associated.
- G1 is the R4 internal schema/semantic screen and must be labelled
  `PROVISIONAL_INTERNAL_G1`, never final canonical acceptance.
- The result contract defines
  `PASS_usable = G0 AND G1 AND G2 AND G3 AND G4`. Because the final frozen evaluator
  criterion and G2/G3/G4 evidence are unavailable, every final `PASS_usable` field and
  count remains `PENDING` with reason
  `CRITERION_NOT_FROZEN_G2_G3_G4_UNAVAILABLE`.
- The eligibility funnel is `U_target=199 -> 129 raw UAS >=4 cells -> 124 height/zstd/
  neighbors -> 96 normal/plane-RMSE -> 94 roughness -> 72 final reference candidates`.
  Its fixed split is development/validation/held-out `51/11/10`. The separate
  `baseline_final=10` 70%-planar diagnostic branch is not the eligibility count.

## Authoritative documents and sealed lineage

1. root `AGENTS.md`
2. `docs/research/00_RESEARCH_CHARTER.md` through
   `docs/research/06_DECISION_LOG.md`
3. `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
4. R3 closed commit `551e633fb9b3f29418a5ba1620c10451b55ddcd6`
5. R4 source/accepted/result/verified/closed chain:
   `9a03711b3c4d4a61717ce7745741152dbc2152d4` ->
   `dab3c749293ca3d7b4503eb3a778a8de266afae4` ->
   `e8f5fa882bc578b743ae7e809bc4f85eb323038f` ->
   `a1524fc07019846eec502e12d7c9a0345b1aecd1` ->
   `c760437bfb50674e11ba1806ef7e7a02e3ca2aa4`
6. `docs/handoffs/returns/P2_C2W_C1_C2_FEASIBILITY_PILOT_FINALIZE_RECOVERY_R4_RETURN_v1.md`
7. `docs/experiments/p2/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/C1_C2_DEVELOPMENT_REPORT_v1.md`
8. `artifacts/manifests/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/technical_result_manifest_v1.json`
9. `docs/research/preregistration/gate_s0/uas_eligibility_explainer_v1/UAS_199_TO_72_EXPLAINER_v1.md`
10. `docs/research/preregistration/gate_s0/uas_eligibility_explainer_v1/uas_eligibility_examples_v1.csv`
11. `docs/research/preregistration/gate_s0/uas_eligibility_explainer_v1/uas_eligibility_explainer_v1.json`

Past packets, Returns, receipts, reports, and manifests are immutable. Any correction
created here must be an additive supplement that links to the protected record.

## Exact reusable inputs

| Input | Exact binding | Permitted use |
|---|---|---|
| Sealed R3 namespace | `artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_feasibility_pilot_recovery_r3_v1/P2-C1-C2-FEASIBILITY-PILOT-RECOVERY-R3-v1/`; closed attestation: 521 regular files, 55,170,598 bytes, 0 symlinks | Resolve only each unit's exact sealed derived `input.las`, `r_derived`, and CityJSON/CityJSONSeq record named in the activation allowlist; render already generated geometry only |
| R4 accepted R3 subset | 22 records, 12,920,322 bytes; identity `46e2da58e177d0aaaba453e316cc8a5d64a24d67b2edc1504299fe22d9ea261f` | Reuse the closed attestation for preflight; no separate hash-only pass. Any needed record is parsed and digested only within its one natural render read |
| R4 result surface | 102 rows in the promoted CSVs and exact R4 technical manifest | Display existing status, metrics, row-to-operation mapping, and fixed cases; no recomputation |
| Compact reference-candidate cells | `artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/uas_reference_coverage_r1_v1/P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1/reference/reference_candidate_cells_v1.csv`; 3,785,261 bytes; SHA-256 `bf87736227ea3c28bc8f966f36e2498f786d2de420a732fa0bfebbb73664275a` | One natural parse-and-digest stream only; select the exact seven fixed-example cell rows, never recompute cells |
| Eligibility candidate ledger | Git blob `6e5d6ab0698c0fdf3e67e74cbdd060bf785ea06b` | Read only already-bound candidate membership, counts, bboxes, and reasons |
| Split ledger | Git blob `f6db7b8accdbd7b57b4a221c441acfc5589fb592` | Confirm 51/11/10 IDs without opening protected outcomes |
| Attrition ledger | Git blob `63344a227c72eefcd8c550e08e123d1b7de050a3` | Display frozen funnel counts only |
| Coverage config | Git blob `64c7beaf5cd7780a4935b23fe96f7b2cd152db96` | Display frozen rule labels only |
| Claim-scope record | Git blob `de7ca06632afe03b01b10c8e6894dab4b7773237` | Preserve claim boundaries |
| Fixed examples | Exact rows in `uas_eligibility_examples_v1.csv` and `uas_eligibility_explainer_v1.json` | Generate the seven fixed panels below; do not substitute examples |

Before activation, the implementation commit must add an exact, minimal allowlist of
the sealed R3 **derived** `input.las`, `r_derived`, and CityJSON/CityJSONSeq records for
the seven unique operation units. Each allowlisted record may be parsed and digested
only in its single natural processing stream; a separate hash-only pass is forbidden.
Broad namespace enumeration is forbidden. Original/raw LAS, raw UAS, raw images, raw
MVS, ALS, LoD1/LoD2 reference geometry, and protected evaluation payloads are not
inputs.

## Frozen fixed-example panel roster

Every panel must show the actual artifact-bound compact reference-candidate cells in
the Git-bound bbox rectangle at a common declared scale, together with support counts,
candidate/fail label, and exact reason. A bbox is a spatial extent, not a roof outline;
the caption must say so. No synthetic or illustrative roof shape may be substituted.

| Panel | building_id | candidate | reference cells | current views | MVS cells | C4 cells | bbox width x height (m) | exact reason |
|---|---|---:|---:|---:|---:|---:|---:|---|
| P1 | `DEBY_LOD2_4959324` | true | 5 | 228 | 97 | 87 | 11.96 x 7.76 | `PASS_ALL_INPUT_SUPPORT_RULES` |
| P2 | `DEBY_LOD2_4959793` | true | 97 | 241 | 282 | 193 | 16.84 x 19.90 | `PASS_ALL_INPUT_SUPPORT_RULES` |
| P3 | `DEBY_LOD2_4959460` | true | 3543 | 399 | 8842 | 6740 | 111.51 x 107.96 | `PASS_ALL_INPUT_SUPPORT_RULES` |
| F1 | `DEBY_LOD2_4907184` | false | 3 | 186 | 521 | 451 | 23.074 x 28.73 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT` |
| F2 | `DEBY_LOD2_4907034` | false | 0 | 61 | 0 | 574 | 52.27 x 28.55 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_MVS_SUPPORT` |
| F3 | `DEBY_LOD2_4908166` | false | 0 | 85 | 40 | 3 | 7.082 x 7.031 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_C4_SUPPORT` |
| F4 | `DEBY_LOD2_4908164` | false | 0 | 63 | 0 | 0 | 8.691 x 6.887 | `INSUFFICIENT_INDEPENDENT_UAS_REFERENCE_SUPPORT;INSUFFICIENT_MVS_SUPPORT;INSUFFICIENT_C4_SUPPORT` |

The exact punctuation/ordering of multi-reason strings must be taken from the bound
compact row, not reconstructed from this prose if they differ byte-for-byte.

## In scope

- Add one reusable deterministic renderer/report script, one frozen config, and tests.
- Resolve each unit's exact allowlisted sealed R3 derived `input.las`, `r_derived`, and
  CityJSON/CityJSONSeq through existing manifests. Parse and digest every record once
  in the rendering stream; do not add a hash-only read.
- Render each unique operation/method geometry once, using geometry only, and reuse
  that render for every R4 row mapped to the same operation. The row index must expose
  this reuse; it must not pretend repeated rows are independent renders.
- Use a fixed CRS, fixed geometry colors, fixed camera rule, fixed viewport/aspect,
  fixed background, and paired common extent. No method-specific auto-zoom or
  outcome-dependent camera choice is allowed.
- Include deterministic top, common-oblique, and principal-section views only if all
  are defined numerically in the config and smoke-tested before activation. If a view
  cannot be generated from allowlisted geometry alone, omit that view class for both
  methods and record the reason; do not open another source.
- Create an explicit blank/missing C2 panel for `DEBY_LOD2_4907183` with the frozen
  association failure reason.
- Create the seven actual eligibility panels in the preceding roster only from the
  artifact-bound compact cells and Git-bound bbox/count/reason records. Parse and
  digest the compact cell artifact once in the panel-generation stream.
- Publish the exact stage funnel and the additive `46/4/1` coverage correction.
- Record every new small output's lineage. When the producing library does not expose
  written bytes (for example, a renderer-managed image write), one post-write digest
  read of that **new output only** is permitted. This exception never applies to a
  sealed input. Reuse sealed R3/R4 attestations and natural processing digests; do not
  add a separate hash-only pass over sealed inputs.

## Out of scope

- Any C3 training or C3/C4/C5 execution.
- Validation or held-out payload access, result access, or display.
- New metric calculation, rescoring, threshold tuning, example selection, ranking,
  statistical inference, or final evaluator freeze.
- Roofer execution, reconstruction, MVS, LiDAR processing, GS training, or surface
  extraction.
- Raw-source reopen; R1, `Images.zip`, `OPF.zip`, raw/original UAS, MVS, ALS, LAS,
  LoD1/LoD2, and original image/pose reads or hashes. The only LAS exception is the
  exact sealed **derived** R3 `input.las` allowlist above, once per unique unit.
- Eligibility recomputation or candidate/split membership changes.
- Texture/imagery/reference overlays, roof semantics, roof type, final GT model, or
  any visual comparison that leaks evaluation-only geometry into an honest arm.
- Modification of an existing packet, Return, receipt, report, CSV, JSON, or manifest.
- A final adapter choice, success count, Gate decision, or scientific verdict.

## Tasks

1. **Preflight and authority.** Fail closed unless the packet is activated through the
   exact two-host receipt chain and the Experiment Host owns the writer turn.
2. **Bind without repeating.** Verify Git blobs and closed receipts read-only. Resolve
   only the activation allowlist. For each of seven unique units, read and digest its
   exact sealed derived `input.las`, `r_derived`, and CityJSON/CityJSONSeq no more than
   once in the natural render stream. Record exactly seven derived operation-LAS
   processing reads/digests, with per-record maximum one, zero separate hash-only
   passes, zero original/raw-source reads/hashes, and zero Roofer/reconstruction
   invocations.
3. **Freeze visual rules before data render.** Run a zero-payload synthetic fixture to
   prove deterministic camera, projection, scale, colors, missing-panel behavior, and
   output bytes. Record renderer/toolchain/image identity.
4. **Render unique sealed operations once.** Generate one view set per unique
   operation/method, then build the 102-row index through references to those files.
   The expected unique operation count is seven; any mismatch stops the task.
5. **Render the frozen eligibility roster.** Generate P1/P2/P3/F1/F2/F3/F4 panels from
   the artifact-bound compact reference-candidate cells and Git-bound bboxes/counts/
   reasons. Assert all seven IDs and all frozen values; do not enumerate raw data or
   recompute eligibility. The compact artifact receives one natural parse-and-digest
   stream and no separate hash-only pass.
6. **Publish the status funnel.** The exact table is:

   | method | denominator | G0 | provisional internal G1 | G2 | G3 | G4 | PASS_usable |
   |---|---:|---:|---:|---|---|---|---|
   | C1_L_upper | 51 | 51 | 51 | PENDING | PENDING | PENDING | PENDING |
   | C2_MVS | 51 | 50 | 50 | PENDING | PENDING | PENDING | PENDING |

   Every pending cell must carry
   `CRITERION_NOT_FROZEN_G2_G3_G4_UNAVAILABLE`. Do not derive a final success count.
7. **Publish an additive correction.** State that the manifest-bound exact C2 coverage
   surface is: 46/50 scored rows full, four partial
   (`4907177`, `4907180`, `4907176`, `4906965`), and one of the 51 denominator rows
   absent/unscored (`4907183`). Explain that the protected R4 Return's phrase
   `47/50 full` is a prose inconsistency; preserve that Return unchanged.
8. **Verify and return.** Run containerized tests, validate the technical manifest and
   handoff receipts, obtain independent scope/ownership/no-repeat reviews, and return
   writer ownership. Keep `scientific_verdict: null`.

## Required outputs

| Output | Path | Required content |
|---|---|---|
| External supplement namespace | `artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_evaluator_backfill_v1/P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1/` | Add-once rendered files, fixed roster panels, logs, and control ledgers only |
| Human-readable supplement | `docs/experiments/p2/c1_c2_qualitative_evaluator_backfill_v1/C1_C2_QUALITATIVE_EVALUATOR_SUPPLEMENT_v1.md` | Interpretation lock, qualitative index, eligibility panels, funnel, correction, limitations |
| Stage funnel | `docs/experiments/p2/c1_c2_qualitative_evaluator_backfill_v1/c1_c2_stage_funnel_v1.csv` | Exact two-row funnel with pending reasons |
| Eligibility examples | `docs/experiments/p2/c1_c2_qualitative_evaluator_backfill_v1/uas_199_to_72_fixed_examples_v1.csv` | Exact seven-row roster and panel resolvers |
| Technical manifest | `artifacts/manifests/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/technical_result_manifest_v1.json` | Input Git blobs/attestations, allowlist, output digests, zero-repeat counters, renderer/toolchain, verdict null |
| Return packet | `docs/handoffs/returns/P2_C2W_C1_C2_QUALITATIVE_EVALUATOR_BACKFILL_RETURN_v1.md` | Exact commits, receipts, artifacts, limitations, reviews, writer return, verdict null |

Rendered binary payloads belong in the external namespace. Git-owned documents must
refer to them through the technical manifest; do not add a second payload copy.

## Verification and fail-closed assertions

- Containerized unit tests cover camera/config determinism, seven-example identity,
  bbox/count/reason equality, 102-row-to-seven-operation reuse, missing C2 behavior,
  stage counts, pending reasons, and `46/4/1` correction.
- The implementation must assert:
  `original_scientific_source_reads_or_hashes=0`,
  `derived_operation_las_processing_reads_and_digests=7`,
  `derived_operation_las_max_reads_per_record=1`,
  `derived_r_derived_max_reads_per_record=1`,
  `derived_cityjson_max_reads_per_record=1`,
  `reference_candidate_cells_processing_reads_and_digests=1`,
  `reference_candidate_cells_hash_only_passes=0`,
  `sealed_derived_input_hash_only_passes=0`, `roofer_invocations=0`,
  `eligibility_recomputations=0`, `new_metric_calculations=0`,
  `validation_payload_accesses=0`, `held_out_payload_accesses=0`, and
  `duplicate_geometry_renders_prevented>0`.
- One post-write verification read may digest each new small output when its producer
  could not digest the bytes during the write. It must not reopen any sealed input.
  The task stops rather than filling a missing source by inference.
- Any mismatch in Git blob, sealed artifact identity, operation count, row count,
  example roster, split access, coverage counts, or renderer rule returns a blocked
  technical status. It does not trigger a retry with broader inputs.

## Preflight

- [ ] The human supplied the complete activation tuple: exact `handoff_id`, exact
      offered-receipt commit SHA, this packet path, exact non-placeholder source
      commit, and `explicit_user_authorization: APPROVED_FOR_EXECUTION`.
- [ ] Packet status and user approval were changed in a reviewed activation commit;
      DRAFT itself is not treated as authority.
- [ ] Experiment Host is clean, fetched `origin/main`, and inspected the remote packet
      and offered receipt read-only before any pull.
- [ ] `git pull --ff-only origin main` reached the exact advertised commit only after
      those checks.
- [ ] The offered manifest validates and an immutable `100-accepted` receipt transfers
      writer ownership before task action.
- [ ] Exact implementation/config/tests, minimal R3 geometry allowlist, project image,
      renderer/toolchain, and bounded runtime/storage caps are committed and named in
      the activated packet.
- [ ] R3/R4 closed receipts and accepted artifact identity match; validation and
      held-out remain protected.
- [ ] `scripts/repository/validate_two_host_handoff.py` passes.

If any item fails, return `DRAFT_OR_UNAUTHORIZED_HANDOFF` or `STALE_TASK_PACKET`
without task execution.

## Stop conditions

- any authority, ownership, commit, blob, receipt, or artifact mismatch;
- need to reopen or rehash a source not in the exact allowlist;
- need to recompute eligibility, scores, or metrics;
- any validation/held-out or evaluation-only geometry access;
- outcome-dependent visual rule, non-deterministic renderer, or operation duplication;
- any request for C3, Roofer, threshold, final acceptance, or scientific decision.

## Done when

The exact supplement, two compact tables, manifest, and Return are committed; all
assertions and independent reviews pass; verified and direct-child closed receipts
return writer ownership to the Work Host; and `scientific_verdict` remains `null`.

## Launcher prompt

```text
This packet is DRAFT. Do nothing unless the user supplies the exact activation tuple:
handoff_id P2-W2C-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1, the exact offered-receipt
commit SHA, this packet path, a non-placeholder source commit, and
explicit_user_authorization: APPROVED_FOR_EXECUTION.

When and only when the tuple is complete, verify the Experiment Host is clean and fetch
origin/main. Before pull, inspect the remote packet and offered receipt read-only. Pull
fast-forward-only only if the remote commit, packet, source commit, receiver, scope, and
approval match exactly. Validate the offered manifest, create the immutable accepted
receipt, and take writer ownership before executing any task action.

Execute only the bounded fixed-rule qualitative/evaluator backfill. Reuse sealed R3/R4
attestations and exact derived outputs. Read each of the seven exact allowlisted derived
R3 `input.las`/`r_derived`/CityJSON records, and the one compact reference-candidate
cell artifact, no more than once in their natural parse-and-digest streams. Do not run
a separate hash pass, reopen or hash original/raw sources, recompute eligibility or
metrics, run Roofer/reconstruction/GS, access validation or held-out, or change
historical records. Keep G2/G3/G4/PASS_usable pending and scientific_verdict null. If
any prerequisite differs, stop with STALE_TASK_PACKET.
```
