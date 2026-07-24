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
