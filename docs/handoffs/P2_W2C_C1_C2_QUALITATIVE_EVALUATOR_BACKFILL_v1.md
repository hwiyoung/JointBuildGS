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

1. exactly 51 deterministic per-building development case sheets, each with fixed C1
   and C2 method panels (102 method panels/association rows total), populated through
   101 associated geometry uses and one explicit C2-absent panel while reading the
   seven sealed unique operation payloads only once each;
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
- The qualitative deliverable has exactly 51 building case sheets and 102 fixed method
  panels/association rows (`51 C1 + 51 C2`). Exactly 101 panels use associated geometry
  (`51 C1 + 50 C2`); the remaining panel is the explicit C2-absent record for
  `DEBY_LOD2_4907183`. Those 101 uses resolve to seven unique sealed operation payloads,
  so natural payload reads are exactly 7 and duplicate payload reads prevented are
  exactly `101 - 7 = 94`.
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
| R4 accepted R3 subset | 22 records, 12,920,322 bytes; identity `46e2da58e177d0aaaba453e316cc8a5d64a24d67b2edc1504299fe22d9ea261f` | Use the closed attestation to construct and cross-check the narrower task allowlist. It does not replace this handoff's protocol-mandated live `100-accepted` verification because the new required set also includes exact derived LAS/`r_derived` records and the compact CSV |
| R4 result surface | 102 rows in the promoted CSVs and exact R4 technical manifest | Display existing status, metrics, row-to-operation mapping, and fixed cases; no recomputation |
| Sealed R3 development controls | `freeze/development_score_association_with_pre_roofer_status_v1.jsonl` (40,739 bytes; SHA-256 `6d899874aad543f382b053e32149a183b4885fe5e869d738fa4762e0ab781cd9`), `freeze/development_score_cells_v1.jsonl` (10,868,613 bytes; SHA-256 `de7c02e2a286fa05c34301aae9de625637cf6fb8c07b5f2969141fd20b0d5a59`), and `freeze/execution_units_v1.jsonl` (5,236 bytes; SHA-256 `52f3b44b981d60ab7fec3afdc818e7b4b39e32f35cf9efebb45475e92b58c9d5`) | One natural parse per exact sealed record under the R4 accepted attestation; association/control only. Development UAS cells are a separate post-hoc `REFERENCE` column and never modify condition geometry |
| Compact reference-candidate cells | `artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/uas_reference_coverage_r1_v1/P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1/reference/reference_candidate_cells_v1.csv`; 3,785,261 bytes; SHA-256 `bf87736227ea3c28bc8f966f36e2498f786d2de420a732fa0bfebbb73664275a` | One natural parse-and-digest stream only; select the exact seven fixed-example cell rows, never recompute cells |
| Eligibility candidate ledger | Git blob `6e5d6ab0698c0fdf3e67e74cbdd060bf785ea06b` | Read only already-bound candidate membership, counts, bboxes, and reasons |
| Split ledger | Git blob `f6db7b8accdbd7b57b4a221c441acfc5589fb592` | Confirm 51/11/10 IDs without opening protected outcomes |
| Attrition ledger | Git blob `63344a227c72eefcd8c550e08e123d1b7de050a3` | Display frozen funnel counts only |
| Coverage config | Git blob `64c7beaf5cd7780a4935b23fe96f7b2cd152db96` | Display frozen rule labels only |
| Claim-scope record | Git blob `de7ca06632afe03b01b10c8e6894dab4b7773237` | Preserve claim boundaries |
| Fixed examples | Exact rows in `uas_eligibility_examples_v1.csv` and `uas_eligibility_explainer_v1.json` | Generate the seven fixed panels below; do not substitute examples |

Before activation, the implementation commit must bind an exact 25-record required
artifact allowlist:

- seven unique operation units x exact sealed derived `input.las`, `r_derived`, and
  CityJSON/CityJSONSeq = 21 records;
- the three exact sealed R3 development controls listed above = 3 records; and
- the exact compact reference-candidate CSV = 1 record.

This is not byte-for-byte the same artifact set as one preceding `300-closed`, so
`closed_attestation_reuse` is not eligible. Under `docs/research/05_HANDOFF_PROTOCOL.md`,
the first `100-accepted` must fully SHA-256 every one of these 25 records once before
push and once again from exact `origin/main` after push. These two protocol verification
passes are required and are not duplicate scientific computation. After they establish
the immutable attestation, renderer execution parses/digests each of the seven logical
operation payloads once from the already verified bytes; `200`, `300`, and successor
validation inherit the attestation and perform zero source rehashes.

Broad namespace enumeration is forbidden. Original/raw LAS, raw UAS, raw images, raw
MVS, ALS, LoD1/LoD2 reference geometry, and protected evaluation payloads are not
inputs.

## Hash and read contract by phase

| Source class | First `100-accepted` | Actual renderer/panel run | `200` / `300` / successor validation |
|---|---|---|---|
| Original R1 15.7 GB inputs, raw UAS, `Images.zip`, `OPF.zip` | 0 reads / 0 hashes | 0 reads / 0 hashes | 0 reads / 0 hashes |
| Entire R3 namespace or any non-allowlisted R3 record | 0 full-namespace/enumeration/hash passes | 0 reads | 0 reads / 0 hashes |
| Exact 25-record required allowlist | 25 pre-push + 25 post-push full-file SHA-256 passes; exactly 2 per record | no acceptance rehash; natural parsing only as bounded below | 0 source full-file hash passes |
| Seven logical operation payloads (21 records) | included in the exact 25-record verification above | 7 logical payload loads; each unit's `input.las`, `r_derived`, and CityJSON/CityJSONSeq is parsed and digested once, then cached | 0 source reads / 0 hashes |
| Three sealed development controls | included in the exact 25-record verification above | one natural parse per record; score cells remain post-hoc reference-only | 0 source reads / 0 hashes |
| Compact reference-candidate CSV | included in the exact 25-record verification above | one natural parse-and-digest stream | 0 source reads / 0 hashes |
| New task outputs | not applicable | producing write plus at most one post-write digest read per new file when required by the library | receipt verifies recorded identity without source rehash |

The unavoidable 50 acceptance file-hash passes (`25 x pre/post`) exist solely because
the protocol requires the receiver to prove the new exact required set before and after
the first accepted-receipt push. They must not be reported as zero, hidden inside the
renderer counters, or repeated at later receipt states.

### Exact `100-accepted` receipt evidence contract

The accepted receipt's `verification.commands` must contain two distinct entries with
these exact labels so PRE and POST cannot be collapsed into one prose claim:

1. `PRE: exact 25-record required artifact allowlist live SHA-256 verification before 100-accepted push`
2. `POST: exact 25-record required artifact allowlist live SHA-256 verification at exact origin/main after 100-accepted push`

The accepted receipt's `verification.tests` must contain exactly one entry for each of
the following exact test names and results:

| exact test name | passed | failed | meaning |
|---|---:|---:|---|
| `exact 25-record pre-push SHA-256 verification` | 25 | 0 | Every exact allowlisted record matched URI/bytes/SHA-256 before accepted-receipt push |
| `exact 25-record post-push SHA-256 verification` | 25 | 0 | The same record identities matched from exact `origin/main` after push |

These are evidence rows, not decorative constants. The receipt generator must populate
`passed` and `failed` from the 25 per-record verification results for that phase. The
launcher and promoter must read the exact committed `100-accepted` receipt and:

1. verify state=`accepted`, level=`artifact_verified`, the task/handoff/commit chain,
   and exact 25-record artifact identity against the activation allowlist;
2. find each exact command and exact test name once, rejecting missing, duplicate, or
   conflated PRE/POST evidence;
3. require PRE `passed=25, failed=0` and POST `passed=25, failed=0`; and
4. derive accepted record/pre/post/total counters from the receipt's artifact records
   and test results. The promoter must not emit `25`, `25`, or `50` merely because those
   values appear in config, packet text, or source-code constants.

Promotion fails closed before writing any Git output if the receipt evidence is absent,
does not derive the required values, or disagrees with the allowlist.

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
  CityJSON/CityJSONSeq through existing manifests. At first `100-accepted`, perform the
  required pre-push and post-push live SHA-256 verification on only the exact 25-record
  allowlist. During renderer execution, parse and digest every operation record once
  in its natural processing stream; do not add another hash-only read.
- Read each unique operation payload once, retain only the bounded in-memory geometry
  needed for its associated rows, and produce one fixed-rule case sheet for each of the
  51 development buildings. Each sheet contains fixed C1/C2 method panels, giving 102
  association rows/method panels. The 101 associated geometry uses share seven cached
  payload loads; the one C2-absent panel contains no geometry. The manifest must expose
  the exact row-to-operation association and reuse; repeated rows must not cause or be
  described as independent payload reads.
- Render each building case separately from the cached geometry with its fixed,
  pre-bound per-building bbox viewport. Only the payload load is reused: final
  per-building rendered case sheets are not reused because their viewports differ.
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
  sealed input after the mandatory first-acceptance pre/post checks. Reuse the resulting
  immutable `100-accepted` attestation and natural processing digests; `200`, `300`,
  and successor validation must not add a source hash pass.

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
- Texture/imagery overlays, roof semantics, roof type, or final GT model. The sealed
  development UAS score cells may appear only in a visibly separate post-hoc
  `REFERENCE` column; they must never be overlaid onto, registered to, crop, alter, or
  otherwise feed a C1/C2 geometry panel.
- Modification of an existing packet, Return, receipt, report, CSV, JSON, or manifest.
- A final adapter choice, success count, Gate decision, or scientific verdict.

## Tasks

1. **Preflight and authority.** Fail closed unless the packet is activated through the
   exact two-host receipt chain and the Experiment Host owns the writer turn.
2. **Accept and bind the exact required set.** Verify Git blobs and closed receipts
   read-only, then resolve only the 25-record activation allowlist. For the first
   `100-accepted`, live-SHA-256 all 25 files once before the receipt push and once after
   the exact `origin/main` push. Record 25 pre-push passes, 25 post-push passes, 50 total
   acceptance passes, and exactly two verification passes per allowlisted record. The
   receipt must preserve the exact distinct PRE/POST command labels and exact test names
   specified above, with `passed=25, failed=0` for each test. Derive those counts from
   per-record verification results; do not write them as unevaluated constants. Record
   zero reads/hashes for original R1/raw inputs and zero whole-R3-namespace passes. Any
   missing/mismatched record or receipt evidence stops before rendering.
3. **Parse without repeating.** After accepted attestation is immutable, load each of
   the seven logical operation payloads once. Parse/digest each unit's exact sealed
   derived `input.las`, `r_derived`, and CityJSON/CityJSONSeq once in that natural
   renderer read and cache it. Parse each of the three controls once and the compact
   CSV once. Do not treat the required `100-accepted` verification passes as renderer
   reads, and do not add another source hash-only pass.
4. **Freeze visual rules before data render.** Run a zero-payload synthetic fixture to
   prove deterministic camera, projection, scale, colors, missing-panel behavior, and
   output bytes. Record renderer/toolchain/image identity.
5. **Build all development sheets from seven reads.** Read each of the seven unique
   sealed operation payloads once. Using the already frozen 102-row association map,
   generate exactly 51 per-building case sheets with 102 method panels: 51 associated
   C1 panels, 50 associated C2 panels, and one explicit blank C2-absent panel for
   `DEBY_LOD2_4907183`. Record `sealed_association_rows=102`,
   `associated_render_uses=101`, `unique_execution_units=7`, and
   `duplicate_payload_reads_prevented=94`. Every building sheet must be a separate
   fixed per-building bbox-viewport render from the cached geometry; do not reuse
   another building's rendered image. Any mismatch stops the task.
6. **Render the frozen eligibility roster.** Generate P1/P2/P3/F1/F2/F3/F4 panels from
   the artifact-bound compact reference-candidate cells and Git-bound bboxes/counts/
   reasons. Assert all seven IDs and all frozen values; do not enumerate raw data or
   recompute eligibility. The compact artifact receives one natural parse-and-digest
   stream and no renderer hash-only pass beyond the mandatory accepted pre/post checks.
7. **Publish the status funnel.** The exact table is:

   | method | denominator | G0 / 51 | provisional internal G1 / 51 | G2 / 51 | G3 / 51 | G4 / 51 | PASS_usable / 51 |
   |---|---:|---:|---:|---|---|---|---|
   | C1_L_upper | 51 | 51 | 51 | PENDING | PENDING | PENDING | PENDING |
   | C2_MVS | 51 | 50 | 50 | PENDING | PENDING | PENDING | PENDING |

   The denominator remains exactly 51 at every stage for both methods; unavailable
   later stages do not shrink it to the generated subset. Every pending cell must carry
   `CRITERION_NOT_FROZEN_G2_G3_G4_UNAVAILABLE`. Do not derive a final success count.
8. **Publish an additive correction.** State that the manifest-bound exact C2 coverage
   surface is: 46/50 scored rows full, four partial
   (`4907177`, `4907180`, `4907176`, `4906965`), and one of the 51 denominator rows
   absent/unscored (`4907183`). Explain that the protected R4 Return's phrase
   `47/50 full` is a prose inconsistency; preserve that Return unchanged.
9. **Verify and return without source rehash.** Run containerized tests, validate the
   technical manifest and handoff receipts, obtain independent scope/ownership/
   no-repeat reviews, and return writer ownership. `200-verified`, direct-child
   `300-closed`, and successor validation must inherit the `100-accepted` attestation
   byte-for-byte and record zero source full-file hash passes. The promoter must accept
   the exact committed `100-accepted` receipt as an explicit input, validate its exact
   commands/tests/artifact records, and derive all accepted verification counters from
   it before any promotion write. Keep `scientific_verdict: null`.

## Required outputs

| Output | Path | Required content |
|---|---|---|
| External supplement namespace | `artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_evaluator_backfill_v1/P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1/` | Add-once rendered files, fixed roster panels, logs, and control ledgers only |
| Human-readable supplement | `docs/experiments/p2/c1_c2_qualitative_evaluator_backfill_v1/C1_C2_QUALITATIVE_EVALUATOR_SUPPLEMENT_v1.md` | Interpretation lock, qualitative index, eligibility panels, funnel, correction, limitations |
| Stage funnel | `docs/experiments/p2/c1_c2_qualitative_evaluator_backfill_v1/c1_c2_stage_funnel_v1.csv` | Exact two-row funnel with pending reasons |
| Eligibility examples | `docs/experiments/p2/c1_c2_qualitative_evaluator_backfill_v1/uas_199_to_72_fixed_examples_v1.csv` | Exact seven-row roster and panel resolvers |
| Technical manifest | `artifacts/manifests/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/technical_result_manifest_v1.json` | Input Git blobs/attestations, exact 25-record allowlist, exact accepted receipt path/commit/test evidence, pre/post counters derived from that receipt, renderer natural-read counters, 200/300/successor zero-rehash counters, output digests, renderer/toolchain, verdict null |
| Return packet | `docs/handoffs/returns/P2_C2W_C1_C2_QUALITATIVE_EVALUATOR_BACKFILL_RETURN_v1.md` | Exact commits, receipts, artifacts, limitations, reviews, writer return, verdict null |

Rendered binary payloads belong in the external namespace. Git-owned documents must
refer to them through the technical manifest; do not add a second payload copy.

## Verification and fail-closed assertions

- Containerized unit tests cover camera/config determinism, seven-example identity,
  bbox/count/reason equality, exactly 51 building case sheets with 102 method panels/
  sealed association rows, exactly 101 associated geometry uses, exactly seven natural
  operation-payload reads, exactly 94 duplicate reads prevented, the one missing C2
  panel, stage denominators/counts/pending reasons, the `46/4/1` correction, and the
  phase-separated acceptance/runtime/successor hash counters below. Receipt/promoter
  tests must prove the exact PRE/POST test names and command labels, success derivation
  from `passed/failed`, and fail-closed behavior for missing/duplicate/mismatched
  evidence; a fixture containing only hard-coded 25/50 manifest counters must fail.
- The implementation must assert:
  `required_artifact_allowlist_record_count=25`,
  `accepted_pre_push_live_sha256_full_file_passes=25`,
  `accepted_post_push_live_sha256_full_file_passes=25`,
  `accepted_total_live_sha256_full_file_passes=50`,
  `accepted_live_sha256_passes_per_required_record=2`,
  `original_r1_15_7gb_reads_or_hashes=0`,
  `raw_uas_reads_or_hashes=0`, `images_zip_reads_or_hashes=0`,
  `opf_zip_reads_or_hashes=0`, `whole_r3_namespace_hash_passes=0`,
  `non_allowlisted_r3_reads_or_hashes=0`,
  `renderer_unique_operation_payload_natural_reads=7`,
  `derived_operation_las_processing_reads_and_digests=7`,
  `derived_operation_las_max_reads_per_record=1`,
  `derived_r_derived_processing_reads_and_digests=7`,
  `derived_r_derived_max_reads_per_record=1`,
  `derived_cityjson_processing_reads_and_digests=7`,
  `derived_cityjson_max_reads_per_record=1`,
  `case_sheet_count=51`, `method_panel_count=102`,
  `sealed_association_rows=102`, `associated_render_uses=101`,
  `c1_method_panel_count=51`, `c2_geometry_method_panel_count=50`,
  `c2_absent_method_panel_count=1`,
  `unique_execution_units=7`,
  `duplicate_payload_reads_prevented=94`,
  `reference_candidate_cells_processing_reads_and_digests=1`,
  `renderer_extra_source_hash_only_passes=0`,
  `verified_200_source_full_file_hash_passes=0`,
  `closed_300_source_full_file_hash_passes=0`,
  `successor_validation_source_full_file_hash_passes=0`,
  `roofer_invocations=0`,
  `eligibility_recomputations=0`, `new_metric_calculations=0`,
  `validation_payload_accesses=0`, and `held_out_payload_accesses=0`.
- `accepted_pre_push_live_sha256_full_file_passes`,
  `accepted_post_push_live_sha256_full_file_passes`, and
  `accepted_total_live_sha256_full_file_passes` must be derived respectively from the
  exact PRE test's `passed`, exact POST test's `passed`, and their sum after both
  `failed` counts are proven zero. `required_artifact_allowlist_record_count` must be
  derived from exact receipt artifact-record equality, not copied from configuration.
- One post-write verification read may digest each new small output when its producer
  could not digest the bytes during the write. It must not reopen any sealed input after
  the protocol-mandated accepted pre/post checks. The task stops rather than filling a
  missing source by inference.
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
- [ ] The offered manifest validates. Before any renderer action, the first
      `100-accepted` performs exactly one live SHA-256 pass per required allowlisted
      record before push and one after exact `origin/main` push; both validations pass
      and the immutable accepted receipt transfers writer ownership.
- [ ] Exact implementation/config/tests, minimal R3 geometry allowlist, project image,
      renderer/toolchain, and bounded runtime/storage caps are committed and named in
      the activated packet.
- [ ] R3/R4 closed receipts and accepted artifact identity match; validation and
      held-out remain protected.
- [ ] The accepted receipt records the exact 25-record allowlist, 25 pre-push and 25
      post-push full-file passes, zero original/raw and whole-namespace hash passes,
      and the contract that `200`/`300`/successor checks inherit rather than rehash.
- [ ] The receipt contains the exact distinct PRE/POST command labels and exact two
      test names from this packet; each test was derived from per-record checks and is
      `passed=25, failed=0`.
- [ ] The launcher passes the exact committed `100-accepted` receipt path/commit to the
      promoter. Before any promotion write, the promoter proves artifact equality and
      derives 25/25/50 from receipt evidence rather than config or constants.
- [ ] `scripts/repository/validate_two_host_handoff.py` passes.

If any item fails, return `DRAFT_OR_UNAUTHORIZED_HANDOFF` or `STALE_TASK_PACKET`
without task execution.

## Stop conditions

- any authority, ownership, commit, blob, receipt, or artifact mismatch;
- need to open or hash a source not in the exact allowlist;
- any accepted verification count other than two live passes per exact allowlisted
  record, or any source rehash requested after accepted attestation;
- missing, duplicate, renamed, conflated, hard-coded-only, or non-derived accepted
  PRE/POST command/test evidence;
- need to recompute eligibility, scores, or metrics;
- any validation/held-out or evaluation-only geometry access;
- outcome-dependent visual rule, non-deterministic renderer, or operation duplication;
- any request for C3, Roofer, threshold, final acceptance, or scientific decision.

## Done when

The exact supplement, 51 case sheets with 102 method panels, two compact tables,
manifest, and Return are committed; all assertions and independent reviews pass;
verified and direct-child closed receipts return writer ownership to the Work Host;
and `scientific_verdict` remains `null`.

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
receipt, and take writer ownership before executing any renderer action. Because this
exact 25-record required set is not identical to one preceding closed artifact set,
the first accepted receipt must run the handoff-protocol verification: live-SHA-256
all 25 exact allowlisted records once before push and once after the exact origin/main
push. Record 25 + 25 = 50 full-file verification passes and two passes per record.
Do not hash original R1/raw UAS/Images.zip/OPF.zip or enumerate/hash the full R3
namespace. In verification.commands, record exactly:
PRE: exact 25-record required artifact allowlist live SHA-256 verification before 100-accepted push
POST: exact 25-record required artifact allowlist live SHA-256 verification at exact origin/main after 100-accepted push
In verification.tests, record exactly one result named
`exact 25-record pre-push SHA-256 verification` with passed=25 and failed=0, and one
named `exact 25-record post-push SHA-256 verification` with passed=25 and failed=0.
Populate those results from the per-record verification outcomes, not constants.

Execute only the bounded fixed-rule qualitative/evaluator backfill. Reuse sealed R3/R4
attestations and exact derived outputs. After accepted verification, read each of the
seven logical operation payloads no more than once: each exact derived R3
`input.las`/`r_derived`/CityJSON record is parsed and digested once, then cached. Parse
the three controls once and the compact reference-candidate CSV once. These renderer
reads are separate from the mandatory accepted-receipt verification counters. Do not
run any additional source hash pass; `200`, `300`, and successor validation must report
zero source rehashes while inheriting the accepted attestation. Do not reopen or hash
original/raw sources, recompute eligibility or metrics, run Roofer/reconstruction/GS,
access validation or held-out, or change historical records. Keep
G2/G3/G4/PASS_usable pending and scientific_verdict null. If any prerequisite differs,
stop with STALE_TASK_PACKET.

Pass the exact committed 100-accepted receipt path and commit to the promoter. Before
any Git output write, the promoter must validate exact receipt lineage, artifact-record
equality, the two exact command labels, and the two exact test rows; derive 25/25/50
from receipt evidence. Reject a receipt or renderer manifest that merely repeats
hard-coded counters without that evidence.
```
