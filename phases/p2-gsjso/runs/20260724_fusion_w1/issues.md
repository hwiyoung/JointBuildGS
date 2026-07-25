# FUS-W1 issues

## FUS-W1-PF-001 — canonical source document missing

- Recorded: 2026-07-24 23:28 KST
- Stage: §0 preflight, pin 5 mount freshness
- Status: BLOCKED
- Repetition count: 1
- Required path: `docs/W_면담정리_생성축재개·시드prior·문헌재조사_20260724.md`
- Evidence: absent from the host checkout, the live `/workspace/JointBuildGS` bind mount, every local Git ref/history path, and searched sibling checkouts.
- Controls: the committed dispatch, `boundary_map_v4_1_ladder.csv`, and the approved quality-axis preregistration have identical host/container SHA-256 values, so the bind mount is live for files that exist; the named 07-24 canonical source itself is unavailable.
- Action taken: stopped before target-queue generation, Gate A, seed preparation, P0′, learning, readout, Roofer, or scoring. No detached/background driver was launched.
- Recovery: supply the named canonical document with a verifiable hash/mtime, then rerun all five pins. Resolve the W1 datum value from that source before Gate A; do not substitute another document without 김휘영's direction.
- Counters: `learning_runs_started=0`, `gate_a_measurements_started=0`, `readout_runs_started=0`, `background_driver_launched=false`.

### Resume disposition — 2026-07-25 00:40 KST

- The document is still absent; the provenance issue is not erased or represented as resolved.
- 김휘영 explicitly authorized continuation from the recorded blocker using the committed dispatch-v3 lock. This is recorded as `user_resume_override`, not as reconstruction or substitution of the missing document.
- The committed resume harness at `71e1a38ce88bbda7a448508cc95942b60402807e` reran all five pins: 5/5 passed or passed with the disclosed caveat; additional coordinate/class/datum, no-active-training, and serial-24g plan guards passed.
- The original BLOCKED manifest remained byte-identical (`sha256=1fff804ea6e30ef2d18f702fb67f4a38c0e225d561840311e685f15d5b4a5c38`).
- Resume preflight receipt: `preflight_resume.json`, `sha256=a38fbaf03999d3d6738dab72ce40024fcad15d608cf52d09bd9cee486c9c1b78`.
- Continuation scope: target resolution and Gate A only. Learning remains forbidden until the per-building LiDAR–image alignment gate passes.
- Counters remain `learning_runs_started=0`, `gate_a_measurements_started=0`, `readout_runs_started=0`.

## FUS-W1-TGT-001 — root-owned provisional target artifacts

- Recorded: 2026-07-25 00:42 KST
- Stage: §1 fixed-output regeneration
- Status: RECOVERED
- Repetition count: 1
- Evidence: the first locked Docker regeneration stopped before target calculation because the two untracked provisional outputs, `w1_targets.csv` and `w1_targets_manifest.json`, were owned by `root:root` with mode `0644`.
- Action: changed ownership of exactly those two untracked generated files to the workspace user through the pinned tools container, then reran the unchanged locked generation command.
- Verification: Docker tests 14/14 passed and `--verify-only` passed; regenerated CSV has 178 unique rows and `sha256=256d376080dca7c496aa3f34c9bcbbd1a8e52d0b25d6e98f7eec388b3f6cc943`.
- Scientific impact: none; no alignment measurement, learning, readout, Roofer, or scoring was started before recovery.

## FUS-W1-ALIGN-DEV-001 — direct-residual proxy rejected before measurement

- Recorded: 2026-07-25 01:25 KST
- Stage: Gate A result-blind implementation review
- Status: RECOVERED BEFORE MEASUREMENT
- Evidence: an independent synthetic audit showed that the draft translation-norm proxy could report a small value even when a strong displaced edge remained. The draft was stopped before any training-image residual was read.
- Recovery: the isolated lock1 implementation reports forward and reverse point-distribution median/P90 in pixels and metres, uses `abs(n_img^T J_xy q_ALS_exposed)` pointwise for metre conversion, retains unmatched observations as censored values, and treats translation only as a diagnostic. Strong-distractor, oblique-q, clean integer, subpixel, and ambiguity regressions are locked in `test_fusion_w1_alignment_gate_lock1.py`.
- Verified implementation: Gate SHA-256 `92380e748a1f86e764bf4736595caa9b329ac1395a8c5a4734f37998ef332311`; config SHA-256 `1ad25404f14cba82b16bc7365ccf1531608fe1e025155cd95686188b16ee5571`; Gate test SHA-256 `e9c0a3c386c75303649997c0519757700c0943025eaf584ad58f6b880eaeb4df`; pinned-Docker Gate tests 16/16 passed.
- Scientific impact: none. `gate_a_measurements_started=0`, `learning_runs_started=0`, `readout_runs_started=0`.

## FUS-W1-ALIGN-DEV-002 — concurrent stale draft writer isolated

- Recorded: 2026-07-25 01:37 KST
- Stage: uncommitted Gate A implementation only
- Status: RECOVERED BY PATH ISOLATION
- Evidence: while the designated writer was performing read-only inspection, the standard draft changed from SHA-256 `a5b499a57ee343e96acf50cb999a0e88a1c1a1cd84894586b1fac3cdf17448f2` to `d0f7a9c53466b0fa84ddd65fabf3b9d367a531619b8cfb3355945ebd8cf6690b`; observed mtime was `2026-07-25 01:34:11.503376424 +0900`. The mixed draft referenced new output variables from an old numerical body and was not executable as a measurement workflow.
- Recovery: all six collision-prone files were moved with the file patch tool to unique `*_lock1` paths; internal config, imports, runtime guard, child argv, wrapper, and tests now bind only those paths. The standard v1 paths were not read or edited after isolation. Checkpoint helper paths remained unchanged because their mtimes/hashes were stable.
- Verification: lock1 Gate/config/test hashes are the values recorded in FUS-W1-ALIGN-DEV-001; runtime guard/test/wrapper SHA-256 are `b5199d01165635997a861b73e8b090aa4fa46a978b824f60135ea3fb5e7578f4`, `85d96ed886ddb176f364c40e052151fb1cee9653f5f31f3f3d15b48c01d9ff35`, and `5f5d22908bbea059f2441eb15725b6cbd5c6bcef3c1a068dd90277d247286dbc`; checkpoint helper/test SHA-256 are `1aea00576caabd1ffdfecc6bcd15a23c7da43e59cd8c9ca04f1592712bc1626b` and `e83108b4d59adea17733210ab9d2584a9adf2f07df0f643da71e7277fc51689b`. Pinned-Docker tests passed Gate 16/16, runtime guard 14/14, checkpoint 10/10.
- Scientific impact: none. The collision affected only untracked, pre-measurement drafts; `gate_a_measurements_started=0`, `learning_runs_started=0`, `readout_runs_started=0`, `scoring_runs_started=0`.

## FUS-W1-ALIGN-DEV-003 — primary direction and metre conversion corrected

- Recorded: 2026-07-25 07:27 KST
- Stage: Gate A result-blind numerical contract review
- Status: RECOVERED BEFORE MEASUREMENT; supersedes the numerical method recorded in DEV-001
- Evidence: an independent audit found that the isolated draft used `max(forward, reverse)` as the official median/P90 and divided pixel residuals by the direction-dependent scalar `abs(n^T J_xy q_ALS_exposed)`. The locked contract instead requires the forward ALS-boundary-to-image-edge point distribution as the primary residual and the pointwise normal-Jacobian row norm `||n^T J_xy||_2` for pixel-to-metre conversion.
- Recovery: `median_residual_*` and `p90_residual_*` now use only the forward distribution, including search-radius-censored unmatched ALS boundary points. Reverse image-edge support remains in separate fields and validity checks only. Matched samples use `||n_edge^T J_xy||_2`; censored unmatched samples use `||n_boundary^T J_xy||_2`; result-blind view selection uses the same boundary-normal row norm.
- Regression locks: direct square-side offsets (median 6 px, P90 7 px rather than translation norm), 40/60 asymmetric median, varying pointwise Jacobians (median 0.30 m, P90 0.68 m), censored unmatched inclusion, wrong-normal rejection, deterministic spatial-null rejection, equal-building weighting under unequal view counts, rank-deficient fail-closed, front/rear z-buffer selection, and footprint perturbation versus class-6 source movement.
- Verification: Gate/config/test SHA-256 are `e640118c37e3909e7c4fea61a18c98355d55c6848956e5cc43be61c7bbdab252`, `db936d742f3933c6d29a7d7ae5796ae63a44470108c7f8439025fb5a10bb55c8`, and `2f30a28f0854beef12f50dad1ec5adc3a0ddf5dae715e4a03d4a032f038f2c30`. The pinned read-only Docker run passed Gate 24/24, runtime guard 14/14, and checkpoint 10/10 (48/48).
- Scientific impact: none. The correction was completed before any training-image Gate residual was read; `gate_a_measurements_started=0`, `learning_runs_started=0`, `readout_runs_started=0`, `scoring_runs_started=0`.

## FUS-W1-ALIGN-RUN-001 — logical image-path aggregate restored

- Recorded: 2026-07-25 07:32 KST
- Stage: first committed Gate A launch, before residual measurement
- Status: RECOVERED BEFORE MEASUREMENT
- Evidence: the runtime guard stopped with `training image aggregate differs from immutable preflight`. The image directory is the locked logical symlink `results/tum_transfer/data_geoidfix/images`; resolving it before constructing `sha256sum` stream labels changed only the path prefix to the physical target. The resulting aggregate was `62760e95b4396192b2cfc2a4a9d32fad029d5d046266b82d2a40d8478f0bdcf0`, while file count and total bytes remained exactly `937` and `910980034`.
- Recovery: the guard still resolves and constrains the directory to the repository for safe file reads, but constructs the hash stream with the immutable logical repo-relative prefix. The recomputed aggregate is `dedc4251e491a9ae40d7c91073410cbf504023b6fe3143238b2528dc3146308a`, exactly matching preflight. A symlink-path regression test was added.
- Verification: runtime guard/test SHA-256 are `e5ab71b2b03c9d5e0f906d8b5015cd9945c0aba07704579cf276553da5a5b73b` and `b512cc04f97b095d2b8bf2db007435fed8b560c0fbdbe5dd1d3a223e6e75ac1c`. Pinned read-only Docker tests passed Gate 24/24, runtime 15/15, checkpoint 10/10 (49/49); a live in-container rehash returned the locked aggregate, count, and bytes.
- Scientific impact: none. The first launch stopped in the runtime guard before view selection or training-image residual measurement; `gate_a_measurements_started=0`, `learning_runs_started=0`, `readout_runs_started=0`, `scoring_runs_started=0`.

## FUS-W1-ALIGN-RUN-002 — unregistered azimuth-bin hard gate removed

- Recorded: 2026-07-25 07:35 KST
- Stage: ALS-only result-blind view selection, before image-edge extraction
- Status: RECOVERED BEFORE RESIDUAL MEASUREMENT
- Evidence: the second committed launch passed the runtime guard, matched the 937-image lock, and loaded class-2/6 ALS for all 28 core targets. It then stopped at `DEBY_LOD2_42364609: observable views span only 3 azimuth bins; required 4`.
- Contract correction: the dispatch locks 10..30 observed training views per building but does not preregister a minimum number of camera-azimuth bins. The draft-only four-bin hard gate was therefore removed. Eight-bin labels and observability-first deterministic round-robin selection remain, so available angular diversity is still maximized and reported without becoming a new eligibility criterion.
- Verification: Gate/config/test SHA-256 are `e8391b59745842c95067bbb6b3dbbf8b25df97eaa7a3b224c2578c92660d5e15`, `d9dd48de14870c091586534a2ab74f55cc5dda515db9811a9363becfcc9654c0`, and `0b946f2153e3339501898d2953542479efb2e5009a3b60cdad63dc392700234d`. Pinned read-only Docker tests passed Gate 24/24, runtime 15/15, and checkpoint 10/10 (49/49).
- Scientific impact: no image intensities, edges, or residual distributions were read before the stop; `edge_residual_views_measured=0`, `learning_runs_started=0`, `readout_runs_started=0`, `scoring_runs_started=0`.

## FUS-W1-ALIGN-RUN-003 — predicted uncertainty retained as ranking, not exclusion

- Recorded: 2026-07-25 07:39 KST
- Stage: ALS-only result-blind view selection, before image-edge extraction
- Status: RECOVERED BEFORE RESIDUAL MEASUREMENT
- Evidence: the third committed launch passed preflight and the corrected azimuth policy but stopped because `DEBY_LOD2_4908051` had only 9 candidates below the draft's predicted 0.30 m uncertainty threshold. The dispatch requires 10..30 observed views and does not define a predicted premeasurement exclusion.
- Contract correction: the 10-view minimum remains unchanged. All projectable candidates satisfying the class-6, boundary, Jacobian-rank, and sensitivity contracts remain eligible; predicted uncertainty is used only for result-blind ordering and reporting. Actual edge-localization uncertainty is measured after edge extraction, and any view above the locked 0.30 m measured limit remains invalid and therefore causes the all-views-valid building gate to fail honestly.
- Verification: Gate/config/test SHA-256 are `1e827c86b6543ac484cce79a0a72b4ccfb37d4288d1d4b700b7fa30717a6903d`, `9a33279145645dadcebbfc9dcaaf90cbc256675f36d04b334b74b303a8601496`, and `770df226a60e66a5833ed1d19441a01d930a6cdea46c84bc6730d5eef07322b1`. Pinned read-only Docker tests passed 49/49; the view-selection regression requires all 16 synthetic views including one whose predicted uncertainty is above the 0.30 m reporting reference.
- Scientific impact: no image intensities, edges, or residual distributions were read before the stop; `edge_residual_views_measured=0`, `learning_runs_started=0`, `readout_runs_started=0`, `scoring_runs_started=0`.

## FUS-W1-ALIGN-RUN-004 — core Gate A stopped after the third consecutive building error

- Recorded: 2026-07-25 07:51 KST
- Stage: core-cohort Gate A direct edge-residual measurement
- Status: BLOCKED; learning entry forbidden
- Execution binding: branch `exp/fusion-w1`, measurement HEAD `f02254ada240189982412ddd2feef1d32db3c345`, checkpoint identity `5acff3750a9b0767d59d64486449d2d5379d5bcd1a8a76f52c1511af0fc54933`, pinned tools image `sha256:87bea02e5598a3d53a119b754191673497d52641bd8ea4106ffee653407579b0`. The runtime guard passed the locked 937-image aggregate (`dedc4251e491a9ae40d7c91073410cbf504023b6fe3143238b2528dc3146308a`) and loaded class-2/6 ALS for all 28 resolved core targets.
- Stop evidence: the first three queue targets (`DEBY_LOD2_42364609`, `DEBY_LOD2_42364659`, `DEBY_LOD2_42364663`) each produced `GateContractError:robust translation IRLS did not converge`. At the third consecutive building, the registered catastrophe rule emitted `STAGE_STOP` and a durable receipt with `status=BLOCKED`, `learning_allowed=false`, and reason `same_error_type_across_three_consecutive_buildings`.
- Measured scope: 3 buildings and 71 selected views (11 + 30 + 30) were measured. The first two buildings have durable residual CSV, summary, overlay, and checkpoint artifacts for 41 rows. The third building completed 30-view computation according to the run log, but its building bundle was not written because the stage-stop exception preceded `complete_attempt`; this immediate-persistence ordering defect is tracked separately and does not change the Gate result.
- Durable numeric evidence: `DEBY_LOD2_42364609` has 2 IRLS-exception rows plus 9 numeric rows, 0/11 valid; numeric medians span 2.321860–5.505480 m (0/9 at or below 0.30 m) and P90 spans 5.002976–9.487371 m. `DEBY_LOD2_42364659` has 3 IRLS-exception rows plus 27 numeric rows, 0/30 valid; numeric medians span 0.083745–1.593135 m (15/27 at or below 0.30 m) and P90 spans 0.553287–3.835880 m. All 36 numeric rows failed at least one non-IRLS validity lock; therefore relaxing only the IRLS diagnostic would not make either building pass.
- Dominant non-IRLS validity observations: the first building's 9/9 numeric rows failed reverse support, P90-minus-median, spatial-null, and both coherence locks. The second building's 27/27 numeric rows failed P90-minus-median and P90 coherence; 26/27 also failed reverse support.
- Integrity: blocked receipt SHA-256 `9bcba8bbc49de566bd784eb030e2ecf59ba9b1252562f9983fcb4e3c81716edb`; execution-guard SHA-256 `eda2d9637b51a3e749f74645760b568274bd30d384617cf35c861996ba484d05`; run-log SHA-256 `bfa210560f2a2c7412d910cdf1ff9f5954dee07b087335c6ed47287231589925`.
- Counters: `edge_residual_buildings_measured=3`, `edge_residual_views_measured=71`, `durable_building_bundles=2`, `micro_registration_attempts=0`, `learning_runs_started=0`, `readout_runs_started=0`, `scoring_runs_started=0`.

## FUS-W1-ALIGN-DEV-004 — terminal building checkpoint now precedes stage-stop raise

- Recorded: 2026-07-25 07:58 KST
- Stage: post-BLOCKED artifact-persistence audit; no measurement rerun
- Status: RECOVERED FOR FUTURE EXECUTION
- Defect: `measure_all_checkpointed` raised the registered three-consecutive-building stage stop immediately after recording the third building's error decision, before calling `summarize_buildings` and `complete_attempt`. The run therefore retained the global error journal and BLOCKED receipt but lost the already computed third-building residual rows and overlay.
- Recovery: the stop decision is now latched, the current building's residual CSV, summary, overlay, and checkpoint are completed and fsynced, and only then is the same `GateContractError` raised. The numeric criteria, error counts, `STAGE_STOP`/BLOCKED receipt generation, and learning prohibition are unchanged.
- Regression lock: a synthetic three-building sequence now asserts that the same error still raises the stage stop and that all three building checkpoints are durable and readable afterward.
- Verification: Gate/test SHA-256 `74a8eda3c321a9e001b25378db4ff4ad990401d32bc08b0c10b5780a7f89ee73` / `80eb6fe0ca42f197511c6949e1a839e20f84158806186a18b76f36d612ac728b`; pinned read-only Docker tests passed Gate 25/25, runtime guard 15/15, checkpoint 10/10 (50/50).
- Run disposition: RUN-004 remains BLOCKED and its third-building bundle is not reconstructed or represented as recovered. No Gate measurement was rerun and no learning/readout/scoring process was started.

## FUS-W1-COREG-LOCK-001 — ALS-fixed camera co-registration preregistered

- Recorded: 2026-07-25 KST
- Stage: post-RUN-004 protocol amendment, before any new ALS/photo residual
- Status: PREREGISTERED; MEASUREMENT NOT YET STARTED
- Authorization: 김휘영 explicitly authorized the proposed alignment while
  requiring preservation of LiDAR as seed and loss source. The verbatim
  authorization and scope are recorded in
  `PROTOCOL_AMENDMENT_V3B_COREG_20260725.md`.
- Root-cause guard: the direct image-edge Gate failure is not treated by itself
  as proof that the camera frame is wrong. Existing read-only 3D evidence
  (`datum_tie.md`) reports a 0.060 m same-surface median height difference and
  auxiliary XY values of 0.00/0.00/-0.01 m, so the locked procedure is
  identity-first and may publish identity when a nonzero SE(3) is not supported.
- Immutable treatment: source ALS LAZ/coordinates/classes/SHA remain fixed,
  EPSG:25832 and zeta 45.700 m remain fixed, scale remains 1, and only the
  camera/photo frame may move. Arm A/B must use the same frozen camera hash.
- Result-blind controls: 36 extension-surface buildings were selected from
  pre-existing W2 support and GroundSurface XY centroids only: fit 18, trigger
  9, independent check 9. Core use is 0; minimum footprint distance to the 28
  core buildings is 20.111315 m. All 36 are calibration-exposed and excluded
  from later extension-only interpretation.
- Capture blocks: original OPF capture time gaps greater than 600 seconds fix
  three blocks before residual measurement: 194, 147, and 596 COLMAP images.
- Verification before measurement: pinned-Docker combined coreg/Gate/runtime/
  checkpoint tests 81/81 passed. Coreg-specific tests are 29/29. They cover
  known small-SE(3) recovery, non-convergence and rank rejection, valid-normal
  filtering, both-surface and exact cohort contracts, exact-once parent chains,
  frozen-selection tamper rejection, full COLMAP binary round-trip, block-pose
  shared-point detachment, pose projection invariance, pivot conjugation,
  quaternion round-trip near 180 degrees, geoid-before-transform, analytic
  Jacobian, input hashes, core exclusion, role counts, and the 937-image block
  inventory. Gate A2 is committed as a distinct zero-micro-registration mode.
- Counters at lock: `new_coreg_residual_buildings=0`,
  `new_coreg_residual_views=0`, `learning_runs_started=0`,
  `readout_runs_started=0`, `scoring_runs_started=0`.

### Execution-process disclosure

- During the read-only design audit, two agent-side host `python3` invocations
  opened existing CSV metadata/header text only, and one later host
  `python3 -m json.tool` invocation parsed the edited Gate config for syntax.
  They wrote no file, loaded no ALS/photo geometry or image intensity, and
  produced no alignment measurement. These were Docker-execution-rule process
  exceptions, not scientific input mutations. Every substantive validation,
  selection, residual measurement, and pose publication command uses the
  pinned Docker images.

## FUS-W1-COREG-RUN-001 — lock1 stopped before trigger residual evaluation

- Recorded: 2026-07-25 KST
- Stage: ALS-fixed camera co-registration, fit complete and trigger sampling
  opened
- Status: BLOCKED; exact-once lock1 will not be resumed
- Execution binding: branch `exp/fusion-w1`, HEAD
  `e21fbe40e042cd72764c00a1f01305bd35f3c830`, coreg config SHA-256
  `2a6e350faa8a1f30b2baa5e64691f0e4a9c7c49c030ec20bb418228ba914c2a4`.
- ALS integrity: class 2/6 materialization contains 3,315,854 points; source
  ALS SHA-256 remained
  `ac5cd0dc9c368a15e1f8fd5a18ad8d96ddbbd8cbaf8e1b608fd675430d6e9225`.
- Fit result: the 18 fit controls produced a valid rank-6 candidate with
  rotation `0.0080702577 deg`, pivot translation `0.1079020267 m`, and maximum
  control displacement `0.1332284124 m`. Neither identity nor the candidate
  passed the fit controls' absolute criteria; both building-balanced medians
  and P90 values were censored at `0.35 m`. Fit values are diagnostic only and
  did not select a transform.
- Stop evidence: after `select_open.json` was written, trigger geometry
  preparation failed closed with
  `controls without both usable roof and ground:
  ['DEBY_LOD2_4907165']`. No `global_selection.json`, trigger residual CSV,
  frozen transform, independent check, or derived pose model was produced.
- Exposure accounting: 18 fit buildings have alignment residuals; trigger
  alignment residuals evaluated `0`. All 36 lock1 controls are
  calibration-selection-exposed, but only the 18 fit buildings are
  alignment-residual-exposed.
- Recovery: v3c creates a fresh lock2 namespace and applies a counts-only
  roof/ground geometry-feasibility screen before assigning roles. Two
  no-residual dry preparations showed that excluding all 36 prior controls
  leaves only 18 feasible buildings, even when all extension tiers are
  admitted. The final exposure-aware split therefore confines all 18 prior
  fit-residual-exposed buildings to lock2 fit and selects trigger/check only
  from buildings with zero prior alignment-residual exposure. It does not
  delete or overwrite lock1.
- Support-screen scope: the screen forms no correspondence or distance
  residual, but it is nominal-alignment-sensitive because it counts both
  sources in a shared footprint crop and tests photo Z support against ALS
  windows. Lock2 fit/trigger/check therefore apply only to this
  support-conditioned population. They cannot replace corrected-camera Gate
  A2 on the predeclared core buildings, and Gate A2 failure still blocks
  learning.
- Predecessor lineage: lock2 now pins and validates the committed lock1
  publication manifest, its exact artifact inventory, fit/select stage
  receipts, select failure receipt, ALS-after hash, and absence of later-stage
  published outputs before accepting the fit-18/trigger-0 exposure account.
- Ledger separation: the two premeasurement preparation failures are retained
  verbatim in `w1_coreg2_prereg_failures.jsonl`; the formal lock2 runtime
  `failures.jsonl` begins empty so prereg exploration is not mixed with
  measurement failures.
- Counters: `learning_runs_started=0`, `readout_runs_started=0`,
  `roofer_runs_started=0`, `scoring_runs_started=0`.

## FUS-W1-COREG2-RUN-001 — no transform satisfied the frozen trigger contract

- Recorded: 2026-07-25 KST
- Stage: exposure-aware ALS-fixed camera co-registration through the
  predeclared three-capture-block fallback
- Status: `BLOCKED`; lock2 is exact-once and will not be resumed
- Calibration scope: the actual 36 controls are all tagged `surface`
  (fit 18 / trigger 9 / unopened check 9); height/outline calibration evidence
  is 0.
- Execution binding: branch `exp/fusion-w1`, measurement HEAD
  `93c0fa679e0a2415393ae8d02a7764415a401c93`, coreg config SHA-256
  `c246b28bf3a87468fe39db2b46fa199b633b263cf317cfc3b1d796d915695f28`.
  The premeasurement verification passed the committed implementation,
  predecessor chain, 937-file depth aggregate, generated locks, ALS hash, and
  fresh formal failure-ledger checks.
- ALS integrity: the fixed materialization contains 3,315,854 class-2/6
  points; the source ALS SHA-256 remained
  `ac5cd0dc9c368a15e1f8fd5a18ad8d96ddbbd8cbaf8e1b608fd675430d6e9225`.
- Global fit: the 18 fit controls produced a valid rank-6 candidate from
  33,969 final correspondences, normalized condition `6.9378544332`,
  rotation `0.0080702577 deg`, pivot translation `0.1079020267 m`, and
  maximum control displacement `0.1332284124 m`. On the fit controls, both
  identity and candidate had building-balanced median/P90 `0.35/0.35 m` and
  `all_buildings_pass=false`. The optimizer's matched-correspondence
  median/P90 was `0.07390/0.20868 m`; the difference from the all-support
  values is due to low unmatched-point coverage and censoring.
- Global trigger: on the nine trigger controls, identity had
  median/P90 `0.1524711988/0.35 m`, minimum support `0.3886435331`, maximum
  absolute bias `0.1274965342 m`, and `all_buildings_pass=false`. The global
  candidate had `0.1224656173/0.35 m`, support `0.4203995794`, bias
  `0.0662427387 m`, and `all_buildings_pass=false`. Its median improvement
  was `0.0300055814 m` (`19.6795%`), below both locked adoption margins
  (`0.05 m` and `20%`). Neither transform was frozen.
- Predeclared block trigger:
  - `capture_block_01`: 7 buildings / 356 observations; median improvement
    `-0.0026994218 m` (`-1.1172%`); not adopted.
  - `capture_block_02`: 4 buildings / 160 observations; median improvement
    `0.0426690996 m` (`32.7081%`), below the locked absolute `0.05 m`
    adoption margin. Candidate P90 remained `0.35 m`, minimum support was
    `0.2461538462`, maximum absolute bias was `0.1212644086 m`, and
    `all_buildings_pass=false`; not adopted.
  - `capture_block_03`: 6 buildings / 571 observations; median improvement
    `0.0 m`; not adopted.
- Stop evidence: `block_selection.json` records
  `status=BLOCKED` and
  `reason=conditional_blocks_do_not_satisfy_full_trigger_contract`. No frozen
  transform, independent-check result, corrected COLMAP model, or pose
  publication manifest exists. Corrected-camera Gate A2 did not start.
- Consumer guard: `block_selection.json` retains a diagnostic matrix field
  even when `choice=none`; it must not be consumed as a selected transform.
  The authoritative guards are `status`, `choice`, empty `block_transforms`,
  and absence of `frozen_transform.json`.
- Wrapper issue: after the scientific block result, the serial wrapper called
  `check` once because `select-blocks` returned a JSON `BLOCKED` status with a
  zero process exit code. `check` failed with `frozen transform is missing`;
  this is a secondary pipeline-control error, not the cause of the block.
- Post-launch audit notes: predecessor-validation failure would currently
  target the lock1 failure ledger before lock2 activation completes, and the
  formal freshness guard checks `failures.jsonl` but not every possible stale
  stage artifact. Neither path occurred in this run: predecessor validation
  passed; the lock1 failure ledger remains SHA-256
  `76a74d7dbc11c2f99006292b865d8edfec903129faec82a12c0dd56f3aacff12`;
  and lock2 began with only its two deterministic ALS-materialization files.
  These guards require correction before any future coreg namespace is
  launched.
- Compact publication manifest SHA-256:
  `4bf6779028161e19efd34a1f3851de3d30689ad4fb8f84f65a87e121e992cfee`.
  The two residual comparison PNGs and all fit/trigger/block numeric artifacts
  are included under `coreg_lock2/`.
- Counters: `learning_runs_started=0`, `gate_a2_runs_started=0`,
  `readout_runs_started=0`, `roofer_runs_started=0`,
  `scoring_runs_started=0`.

## FUS-W1-COREGDIAG-001 — Gate A 사전등록 초과 구현 확인

- Recorded: 2026-07-25 KST
- Stage: learning-zero Gate A diagnostic
- Status: RECORDED; 기준 변경·transform 채택·학습 재개 없음
- 원 발주 관문 A의 수치 조건은 동별 잔차 중앙 `≤0.3 m`였으나,
  `coreg_lock2` 선택 계약은 동별 중앙 `≤0.15 m`, censored P90
  `≤0.3 m`, 지지율 `≥0.7`, 최대 절대 bias `≤0.1 m`를 동시에
  요구하고 후보 채택에 절대 `0.05 m` 및 상대 `20%` 개선폭을 추가했다.
  따라서 P90·지지율·bias·개선폭을 원 관문 판정 조건으로 사용한 부분은
  사전등록 문안을 초과한 구현이다.
- 측정량도 원 문안의 학습 뷰별 ALS 지붕 경계↔영상 에지 직접 잔차가
  아니라 영상 유래 dense DIM/MVS 3D 점군↔ALS의 양방향
  point-to-plane 잔차다. 둘은 같은 이름으로 대체하지 않는다.
- 진단에서는 원 수치 0.3 m를 유지하고, 사전 잠금한 보정 전 대응수
  문턱 `n≥40`의 132동에서 conditional matched 중앙을 표로
  분리했다. P90·censored P90·지지율은 보조 통계로만 기록했다.
- Counters: `learning_runs_started=0`, `readout_runs_started=0`,
  `roofer_runs_started=0`, `scoring_runs_started=0`.

### T4 조건부 이슈 — 사람 검수 전 보류

- Recorded: 2026-07-25 KST
- Stage: low-support × tier auxiliary diagnostic
- Status: OBSERVATION ONLY; 조건부 이슈 ID를 부여하지 않음
- 대응 가능 132동 안에서 보정 전 지지율 nearest-rank Q25
  비반올림값 `0.200652528548124` 이하를 low-support로 잠갔다
  (CSV 표시값 `0.200652528548`). 높이+윤곽은
  low/not-low `7/13`, 표면은 `26/86`이었고, 양측 Fisher exact는
  odds ratio `1.7811`, `p=0.2716`이었다.
- 전 178동의 기술 집계는 높이+윤곽
  `대응 불가/가능-low/가능-not-low=44/7/13`, 표면
  `2/26/86`이다. 수치만 기록하며, “지지율 요구의 범주 오류” 등재
  여부는 김휘영 검수에 남긴다.

## FUS-W1-COREGDIAG-002 — 지지율 요구의 범주 오류 확정

- Recorded: 2026-07-25 KST
- Stage: learning-zero Gate A v2 registration prerequisite
- Status: CONFIRMED by the human preregistration decision; 수치 기준 완화가 아니라 측정 모집단 정정
- 대응 불가 46동의 층 분포는 표면 2·높이 11·윤곽 33이다. 대응 가능 132동 내부의 low-support×층 검정은 Fisher OR 1.7811, p=0.2716이었다.
- `docs/사전등록_관문A_v2·SE3채택재판정_20260725.md` §5에 따라, 무텍스처 동의 영상 증거 부재를 정합 실패로 오독한 지지율 요구를 범주 오류로 기록한다. P90·censored P90·지지율은 관문 A v2의 보조 기록만이며 판정 조건이 아니다.
- Counters at adoption publication: `learning_runs_started=0`, `readout_runs_started=0`, `roofer_runs_started=0`, `scoring_runs_started=0`.

## FUS-W1-COREG-ADOPT-001 — 전역 SE(3) 채택 재판정 기록

- Recorded: 2026-07-25 KST
- Stage: R1 corrected-pose publication before Gate A v2 registration
- Status: ADOPTED by 김휘영 under `docs/사전등록_관문A_v2·SE3채택재판정_20260725.md` §4; downstream interpretation 없음
- lock2의 기존 채택 계약은 중앙 개선 `0.0300055814 m` (`19.6795%`)로 잠금 마진 `0.05 m`와 `20%`에 모두 미달해 `choice=none`·미동결이었다. 이번 채택은 그 계약을 재적용한 결과가 아니라 §4의 별도 인간 판정이다.
- 채택 변환은 `fit_candidate.candidate_photo_to_als_global_pivot_matrix`에서 직접 읽은 전역 SE(3)이며, 회전 `0.0080702577°`, 이동 `(+0.040581, +0.020840, −0.097784) m`, rank 6, 최종 대응 33,969이다. 937개 카메라 포즈에 동일 변환을 1회 적용하고 블록별·동별 변환은 적용하지 않는다.
- 원 sparse 모델·ALS LAZ·영상 픽셀·footprint·참조 GML은 수정하지 않고, `ζ=45.7 m`를 다시 적용하지 않는다. 보정판은 별도 경로에 발행하며 arm A/B는 동일한 보정판 `images.bin` SHA-256을 소비해야 한다.
- R1 manifest는 왕복·투영 불변·카메라 중심·원본 전후 해시·진단 재현 `132/132`, 핵심 `24/24`, 동별 중앙의 중앙 `0.0723671171799 m`, T5 총 잔차 `0.004186 m` 검증표를 기록한다.
- Counters at adoption publication: `learning_runs_started=0`, `readout_runs_started=0`, `roofer_runs_started=0`, `scoring_runs_started=0`.

## FUS-W1-PREPROCESS-001 — 투영 TIN 화면 토폴로지 구현 오류

- Recorded: 2026-07-26 07:14 KST
- Stage: §3 smoke seed/supervision preparation for `DEBY_LOD2_42364609`
- Status: RESOLVED in commit `d8af989`; 최초 실패 staging 보존, 원본 입력 불변
- 최초 실행은 `DJI_20241217084827_0177_D.JPG`에서
  `projected TIN topology is invalid: Triangulation is invalid`로 중단됐다.
  해당 실행은 `views.csv`와 seed 3종까지만 고유 `.staging/` 경로에 남겼고,
  동별·stable `preprocess_manifest.json`은 발행하지 않았다.
- 보존 데이터의 첫 실패 뷰에서 화면 투영 삼각형은 class 6
  `483/483`, class 2 `14,801/14,801`가 모두 negative winding이었고,
  positive winding과 화면 퇴화 삼각형은 각각 0개였다. 오류는
  `matplotlib.tri`의 평면 mesh topology 제약과 투영 삼각형의 방향·겹침이
  충돌한 구현 문제이며, ALS–카메라 정합 잔차나 원본 ALS 분류의 실패로
  기록하지 않는다.
- 화면 mesh 탐색을 겹침·뒤집힘을 허용하는 deterministic
  per-triangle barycentric nearest-z rasterizer로 교체했다. Docker 회귀시험
  `16/16`을 통과했고, 보존 seed와 30뷰의 class 6/2 총 60 raster 읽기 전용
  검증은 `4.27 s`였으며 유효 픽셀 합은 class 6 `4,683`, class 2
  `166,402`였다.
- 재실행은 새 고유 staging을 사용해 `PARTIAL` stable manifest와
  `w1_seed_stats.csv` 1행을 발행했다. 실제 시드는 입력/출력 `7,993/7,993`
  점, class 2/6 `7,644/349`, 다운샘플 없음, RGB 미표본 0점이다.
- 이 오류와 수정 동안 `learning_runs_started=0`; ALS LAZ·영상·원 포즈·
  보정 포즈·footprint·참조 GML은 수정하지 않았다.

## FUS-W1-CUTOFF-001 — 06:30 컷 시점 신규 학습 미착수

- Recorded: 2026-07-26 07:15 KST
- Stage: §7 cutoff transition
- Status: PARTIAL CLOSEOUT; 해석·판정 없음
- 잠금된 컷은 `2026-07-26T06:30:00+09:00`이며, 현재 호스트 시각 확인 시
  이미 컷 이후였다. 완료 또는 진행 중인 30k 학습이 없었으므로 새 학습을
  시작하지 않았고 `learning_runs_started=0`을 유지했다.
- 컷 이후 실행 범위는 위 전처리 구현 오류의 수정·재검증, 첫 동의 실제
  투입 시드 P0′ 조립·채점 1회, 고정 형식의 부분 집계·보고 발행으로
  제한했다. 학습 후 pointcloudification/readout은 시작하지 않았다.
- P0′ 1동은 Roofer 1회와 scoring 1회를 완료해 LoD2 조립 성공 및
  val3dity 유효를 각각 기록했다. 이는 학습 전 시드 귀속 통제이며
  arm A/B 학습 결과나 눈금 1~4 판정값으로 사용하지 않는다.

## FUS-W1-TRAIN-ENV-001 — gsplat JIT 캐시 쓰기 권한 오류

- Recorded: 2026-07-26 08:13 KST
- Stage: §7 smoke `DEBY_LOD2_42364609` arm A r1, 30k launch
- Status: INFRASTRUCTURE RETRY AUTHORIZED; 원 실패 보존, 재시도 미착수
- 최초 Docker 프로세스는 데이터·30뷰·시드 7,993점·depth/normal 감독을
  읽고 optimizer step 1 이전 gsplat CUDA extension lazy build에서
  `PermissionError: [Errno 13] Permission denied: '/.cache'`로 4.31초 만에
  종료했다. 이는 ALS–영상 정합이나 학습 수렴 오류로 기록하지 않는다.
- `full_state_manifest.json`은 `learning_runs_started=0`,
  `start_completed_steps=0`, `last_completed_steps=0`, checkpoint 없음이며,
  loss CSV도 생성되지 않았다. 따라서 과학적 학습 런은 시작되지 않았다.
- 원 기록 SHA-256은 `started.json`
  `1e926bfdb96e33d1bcb77fd28b69e26102413fd5deb4be76459d9fd8988bf9f3`,
  `failed.json`
  `729c0d76a2468bd8f1c7e2c49f26ba32251e1ea51f48418070bce19048b59ecf`,
  `training.log`
  `bd3fbc73e8535a5062b9d06fac6f6d3714ca3112b33a446d18c4b4df9aaea817`,
  `full_state_manifest.json`
  `29e9023353c15a15072339b831c767e72f2245f5d90ee3ffd4657ff5c5f9a60d`다.
- 승인된 1회 재시도는 원 파일을 삭제·덮어쓰지 않고
  `infra_retry_01/` 별도 namespace를 사용한다. 원 resolved config에서
  허용되는 차이는 출력 경로 `out_dir` 하나뿐이며 seed 1001·arm A recipe·
  30k·입력·포즈·감독은 동일하다. 컨테이너 환경만 job 내부 쓰기 가능
  `HOME`, `XDG_CACHE_HOME`, `TORCH_EXTENSIONS_DIR`로 고정한다.
- 재시도는 exclusive receipt로 한 번만 claim하며, 현재 HEAD는 원
  materialization HEAD `52aed8bd35066beb0bc8f0ce254e17df9187444e`의
  정확히 한 커밋 후속이고 그 커밋의 경로가 retry 정책 allowlist와
  일치할 때만 허용한다.
- retry 정책은 위에 기록한 원 `started.json`·`failed.json`·`training.log`·
  `full_state_manifest.json`의 SHA-256을 각각 고정하며, claim 전에 네 파일의
  현재 바이트가 모두 일치해야 한다. 단순 상태 필드·로그 marker 일치만으로는
  원 실패를 대체할 수 없다.
- 후속 readout은 원 `failed.json`을 삭제하지 않는다. 대신 root
  `completed.json`이 검증된 `infra_retry_01` started/completed receipt chain을
  SHA-256으로 결속하고, 30k checkpoint·final checkpoint·full-state manifest가
  정확히 원 job의 `infra_retry_01/` 아래에 있을 때만 그 성공 산출물을 소비한다.
  임의 외부 경로, retry receipt hash drift, job-key 불일치에는 기존 failed
  receipt 차단을 유지한다.
- 이 호환성 검증과 함께 readout의 정적 입력 잠금은 현재 커밋된 training
  config와 P0′ driver의 실제 SHA-256으로 갱신했으며, recipe·시드·입력·점수
  정의에는 변경이 없다.
