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
  checkpoint tests 78/78 passed. Coreg-specific tests are 26/26. They cover
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
  alignment residuals evaluated `0`; all 36 lock1 controls are nevertheless
  treated as calibration-exposed and excluded from recovery.
- Recovery: v3c creates a fresh lock2 namespace, excludes all 36 lock1 controls,
  and applies a counts-only roof/ground geometry-feasibility screen before
  assigning fit/trigger/check roles. It does not delete or overwrite lock1.
- Counters: `learning_runs_started=0`, `readout_runs_started=0`,
  `roofer_runs_started=0`, `scoring_runs_started=0`.
