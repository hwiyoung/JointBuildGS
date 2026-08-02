# Codex-to-Work Return — P2 C1/C2 qualitative evaluator backfill v1

## Return metadata

- handoff_id: `P2-W2C-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1`
- task_id: `P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1`
- source implementation commit: `0f9b2e120f81f733e7312e0b9bfd000de726b192`
- activation commit: `814e93c50a01d06a6a882fdeb7e40c4d044ef06f`
- offered commit: `d5afe6d789a0d5133d58e3c8115353b963c2c70c`
- accepted commit: `38c04093d9d67e287c9fd2b88bab278e758ed4c3`
- output/Return commit: `SELF`
- 200 receipt: `PENDING_SEPARATE_200_BLOCKED_EVENT`
- 300 receipt: `PENDING_DIRECT_CHILD_300_CLOSED_EVENT`
- run_id: `P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-RUN-v1`
- execution_mode: `QUALITATIVE_EVALUATOR_BACKFILL_REUSE_ONLY`
- project image: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- completed_at: `2026-08-02T17:45:29+09:00`
- proposed technical status: `BLOCKED_ELIGIBILITY_EXACT_REASON_RENDER_CLIPPING`
- scientific_verdict: `null`

## Answer first

The exact activated reuse-only renderer and promoter completed and wrote the expected
51 development sheets, 102 method panels, compact status tables, technical manifest,
and one seven-cell `199 -> 72` example figure. The numerical, lineage, access and
no-repeat contracts all match the activated packet. Containerized unit tests also pass.

The required post-render human inspection nevertheless found a fail-closed renderer
rule mismatch in `eligibility_199_to_72_fixed_cells_v1.png`: the exact long reason text
for all four excluded examples F1/F2/F3/F4 is not contained legibly in its own panel.
F1 is clipped at the right image boundary; F2 and F3 run into neighboring panel space
and are visibly truncated/overdrawn; F4 spans outside its intended axes. The renderer
places each unwrapped reason at axes coordinate `(0.01, 0.01)` without text wrapping
or a bounds assertion. This is not a display-tool scaling artifact: it is present in
the original 2520 x 1260 PNG pixels. Separately, the containerized synthetic test run
emits `constrained_layout not applied because axes sizes collapsed to zero` at the
eligibility save path; that warning is test evidence, not asserted to be a captured
production-render log.

The packet requires every eligibility panel to show the exact reason and says any
renderer-rule mismatch returns blocked technical status. Therefore this Return does
not claim `200-verified`. The add-once namespace and generated Git records are
preserved as blocked execution evidence without overwrite or rerun. Correct closure
is an attestation-inheriting `200-blocked` followed by direct-child `300-closed`, both
without source-artifact rehash, returning writer ownership to Work Host.

## Authority, acceptance and ownership

- Root `AGENTS.md` and the full canonical `docs/research/00_*.md` through `06_*.md`
  contract set were read. Legacy `EXPERIMENT_PLAN.md` and `RESEARCH_CONTEXT.md` were
  not used as authority.
- The worktree was clean before fetch. The remote packet and `000-offered.json` were
  inspected with `git show` at the exact offered commit before pull.
- Source ancestry and the exact activation tuple were proved read-only. The offered
  receipt validator passed before the fast-forward-only pull.
- `HEAD` was fast-forwarded only to `d5afe6d789a0d5133d58e3c8115353b963c2c70c`.
- The add-once `100-accepted.json` transferred exclusive writer ownership at commit
  `38c04093d9d67e287c9fd2b88bab278e758ed4c3`.
- The accepted artifact set is exactly 25 records and 30,432,763 bytes. Its exact
  separately named PRE-PUSH and POST-PUSH `EXACT 25-RECORD ALLOWLIST` validations
  each passed 25 and failed 0, for 50 acceptance SHA-256 verifications total.
- Acceptance did not hash original R1 15.7 GB inputs, raw UAS, `Images.zip`,
  `OPF.zip`, or the whole R3 namespace. No source full-file hash pass was made after
  the accepted post-push verification.
- Exact `HEAD == origin/main == 38c04093d9d67e287c9fd2b88bab278e758ed4c3`
  was proved before execution.

## Execution and exact output counts

External namespace:

`artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_evaluator_backfill_v1/P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1/`

Physical Experiment Host path:

`/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2-baselines/c1_c2_qualitative_evaluator_backfill_v1/P2-C1-C2-QUALITATIVE-EVALUATOR-BACKFILL-v1/`

The add-once namespace has 54 regular files and 34,226,920 content bytes, below the
2,000,000,000-byte task cap. It contains 51 building PNGs, one eligibility PNG,
`fixed_view_manifest_v1.json`, and `stage_and_coverage_correction_v1.csv`.

| Contract item | Observed |
|---|---:|
| development case sheets | 51 |
| method panels / sealed association rows | 102 / 102 |
| associated geometry uses | 101 |
| C1 panels | 51 |
| C2 geometry / explicit absent panels | 50 / 1 |
| unique operation units | 7 |
| duplicate payload reads prevented | 94 |
| accepted PRE / POST / total SHA-256 evidence | 25 / 25 / 50 |
| operation LAS natural reads and digests | 7, maximum 1 per record |
| `r_derived` natural reads and digests | 7, maximum 1 per record |
| CityJSONSeq natural reads and digests | 7, maximum 1 per record |
| compact reference CSV natural reads and digests | 1 |
| source rehashes after acceptance | 0 |

The stage surface is exact:

- C1 G0/G1: `51/51` and `51/51`;
- C2 G0/G1: `50/51` and `50/51`;
- C2 scored coverage: `46/50` full and `4/50` partial, with partial IDs
  `DEBY_LOD2_4907177`, `DEBY_LOD2_4907180`, `DEBY_LOD2_4907176`, and
  `DEBY_LOD2_4906965`;
- absent/unscored: `1/51`, `DEBY_LOD2_4907183`;
- every G2/G3/G4/`PASS_usable` cell is `PENDING` with reason
  `CRITERION_NOT_FROZEN_G2_G3_G4_UNAVAILABLE`.

## Visual inspection and qualitative observations

All 51 building sheets were decoded and inspected at their original 2100 x 1820
resolution, and the one seven-cell eligibility figure was inspected at its original
2520 x 1260 resolution.

- building sheets decoded: `51`; decode failures: `0`; corrupt files: `0`;
  unintended fully blank sheets: `0`;
- building method panels inspected: `102`; intended explicit blank C2 panel: `1`;
- eligibility example cells inspected: `7`; missing/corrupt cells: `0`;
- eligibility cells with exact-reason layout failure: `4` (`F1`, `F2`, `F3`, `F4`);
  required eligibility figure files affected: `1/1`;
- fixed paired extents, projection and view classes are visually consistent across the
  51 sheets; the C1 panels visibly retain `SELF_REFERENCE_UPPER_BASELINE` labeling;
- the independent UAS reference is a visibly separate first-column post-hoc display
  and is not overlaid into C1 or C2 geometry;
- some fixed principal-section views truthfully show
  `NO_POINTS_IN_FIXED_SECTION_BAND`; these are explicit data-availability annotations,
  not corrupt panels;
- `DEBY_LOD2_4907183` contains the required blank C2 method area labeled
  `UNASSOCIATED_CONDITION_COMPONENT`;
- without making a performance judgment, C2 views are sometimes visibly less
  populated or flatter than paired C1 views, and the four manifest-bound partial rows
  visibly have reduced or incomplete C2 support. These are descriptive observations
  only.

The seven eligibility cells contain the exact P1/P2/P3/F1/F2/F3/F4 IDs, bboxes,
candidate labels, counts and underlying reason strings in the companion CSV/manifest.
The blocked status is specifically about legible display of the exact excluded reason
inside the PNG panels, not about roster/count identity or a new eligibility result.

## Scope, leakage and no-repeat outcome

- C1 remains a self-reference upper baseline and is not independent-reference accuracy
  evidence.
- UAS cells remain post-hoc score/display reference only and do not derive, crop,
  register or change C1/C2 geometry.
- Roofer, reconstruction, MVS processing, LiDAR processing, GS and C3/C4/C5
  invocations: `0`.
- eligibility recomputations and new metric calculations: `0`.
- validation accesses and held-out accesses: `0 / 0`.
- original scientific source reads/hashes and original large-source hashes: `0 / 0`.
- successor 200/300 source rehashes: `0`.
- `scientific_verdict` remains `null`.

The launcher file itself was not executable, so the literal direct shell invocation
first returned permission denied before entering task logic. Invoking it through Bash
then exposed a Git safe-directory ownership check in the authority-only container;
two authority-only starts stopped before output namespace creation or source access.
The successful invocation used a temporary host-side `docker` PATH shim, outside the
repository and artifact roots, solely to inject Git `safe.directory=/workspace` into
the launcher's containers. The shim was removed after completion. There was exactly
one renderer/promoter execution and no scientific-source reopen or retry.

## Containerized verification

The exact project image ran both committed modules:

```text
python -m unittest \
  tests.p2_baselines.c1_c2_qualitative_evaluator_backfill_v1.test_fixed_view_qualitative \
  tests.p2_baselines.c1_c2_qualitative_evaluator_backfill_v1.test_promotion_and_wrapper
```

Result: `Ran 9 tests ... OK`. The same run emitted the Matplotlib warning
`constrained_layout not applied because axes sizes collapsed to zero` from both the
case-sheet and eligibility save paths. The deterministic assertions do not test text
containment, which explains why unit tests pass while original-pixel inspection finds
the eligibility reason-layout failure.

## Independent post-run reviews

- Scientific scope, C1 self-reference and leakage:
  `PASS_SCOPE / FAIL_RENDER_RULE / BLOCKED_CLOSURE_REQUIRED`. The reviewer confirmed
  C1 self-reference labeling, separate post-hoc UAS reference, exact pending evaluator
  state and zero prohibited access/execution. All seven eligibility records are bound
  correctly, but the required PNG does not legibly contain the F1-F4 long reason text.
- Two-host ownership and receipt chain:
  `PASS_CHAIN_AND_SCOPE / BLOCKED_SUCCESSOR_REQUIRED`. The reviewer confirmed exact
  source -> activation -> offered -> accepted ancestry, equal ordered 25-record
  attestation and 30,432,763 bytes, exact 25/0 PRE plus 25/0 POST evidence, and only
  five pending task-owned Git files. The required close is output/Return commit,
  attestation-inheriting `200-blocked`, then direct-child `300-closed` changing only
  that receipt and returning writer ownership.
- Reproducibility, allowed paths and no-repeat:
  `PASS_COUNTS_PATHS_NO_REPEAT / FAIL_ELIGIBILITY_TEXT_CONTAINMENT`. The reviewer
  confirmed 51/102/101/7/94, 46/4/1, 54 external files, zero symlinks, 34,226,920
  content bytes, one natural read per permitted record, zero later source rehash and
  zero prohibited access. The reviewer independently tied the original-pixel defect to
  the unwrapped 2 x 4 renderer text layout and the missing bounds regression test.

All three reviews were mutually independent and read-only. They made no repository
edit, did not invoke the launcher, and did not open or hash the 25 accepted source
records.

## Git outputs preserved as blocked execution evidence

- `docs/experiments/p2/c1_c2_qualitative_evaluator_backfill_v1/C1_C2_QUALITATIVE_EVALUATOR_SUPPLEMENT_v1.md`
- `docs/experiments/p2/c1_c2_qualitative_evaluator_backfill_v1/c1_c2_stage_funnel_v1.csv`
- `docs/experiments/p2/c1_c2_qualitative_evaluator_backfill_v1/uas_199_to_72_fixed_examples_v1.csv`
- `artifacts/manifests/p2_baselines/c1_c2_qualitative_evaluator_backfill_v1/technical_result_manifest_v1.json`
- this Return packet

No historical packet, Return, receipt, report or manifest was modified. The generated
supplement and manifest describe the renderer's bounded output but do not override this
post-render fail-closed disposition. The external namespace must not be overwritten or
rerun. A correction requires a new reviewed implementation/task/run/result identity
and add-once namespace with wrapped or otherwise contained exact reason annotations
plus an automated text-bounds regression assertion.

After independent reviews, preserve the accepted artifact object byte-for-byte in an
immutable `200-blocked`, then create a direct-child `300-closed` changing only that
new receipt, validate the full chain without `--artifact-root`, and return writer
ownership to Work Host.

`scientific_verdict` remains `null`.
