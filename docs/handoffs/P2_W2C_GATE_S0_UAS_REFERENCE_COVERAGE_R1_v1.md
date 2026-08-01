# P2 Gate S0 independent-UAS reference coverage R1 — DRAFT

- task_id: `P2-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1`
- handoff_id: `P2-W2C-GATE-S0-UAS-REFERENCE-COVERAGE-R1-v1`
- status: `DRAFT_NOT_EXECUTION_AUTHORITY`
- predecessor closed commit: `5715a4a55986fc79e6e157ccbf69405102fd2198`
- predecessor accepted/source commit: `853f52c8d843fa8c9bc8d79f62e3e24e1eef10c7`
- Gate S0 decision: `null`
- scientific_verdict: `null`
- C1--C5 performance: `PROHIBITED`

## Answer first

The recovered freeze fixes the exact AOI, `U_target=199`, common source
`962/937/25`, condition inputs and split machinery, but its independent evaluation
reference leaves only `E_paired=10` in three spatial/reference groups. The held-out
three buildings belong to one group. That is useful for a bounded feasibility pilot,
not for stable population-level C1--C5 efficacy, generalization or subgroup claims.

The dominant loss is not C5 availability. Exact input-side coverage is image views
199/199, MVS 152/199, C4 188/199 and C5 199/199. The independent UAS rule drops
buildings with at least four candidate cells from 89 to 12 at its preliminary-
component planar-fraction gate and then to 10 at final component/score support.

This DRAFT authorizes no source read or execution. Its proposed next task is one
outcome-free reference-coverage calibration using only the already checkpointed
compact UAS grid. It must decide whether a scientifically defensible reference and
split candidate exists; it must not maximize building count or silently promote the
diagnostic 72-building alternative.

## Frozen invariants

The task may not alter:

- AOI EPSG:25832 bbox
  `[690791.74, 5335864.05, 691154.65, 5336353.85]` and its canonical 199 stable IDs;
- exact common source `B_CURRENT_CANDIDATE_c205892c390997b5` with 962 images,
  937 registered image/pose pairs and 25 excluded images;
- the common consumer set `cameras.bin`, `images.bin`, `points3D.bin` and
  `dim_dense.ply`, or the READY/READY_OFF component choices;
- C4 ALS input identity/alignment and the exact 199 C5 LoD1 priors;
- C5 labels `REFERENCE_DERIVED_DIAGNOSTIC_ONLY` and
  `REFERENCE_DERIVED_SELF_CONDITIONED`, with independent UAS required for primary
  scoring;
- the prohibition on LoD2 `RoofSurface`, roof type, semantic labels, C1--C5 method
  outcomes or UAS roof geometry in C3--C5 registration;
- terrain-normalized/relative primary evaluation and disabled absolute-Z metrics;
- protected held-out outcomes, Fusion W1, `R_ext` and all performance results.

The task may amend `E_paired` and split IDs only if a new reference rule passes this
packet's outcome-free QA and is subsequently accepted by a separate human Gate S0
decision. The present `E_paired=10` remains the latest technically recorded set until
then.

## Reusable evidence and no-repeat contract

The exact compact inputs proposed for this task are:

- grid URI: `artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/reference/c1_grid_v1.npz`;
  bytes `3,023,643`; SHA-256
  `4f72178551e25ef27a952a09faa8331c1464416fcd6c5f66a57a9424e7f0b77b`;
- source-checkpoint URI: `artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/050-c1_reference_frozen_pre_c5.json`;
  bytes `3,140`; SHA-256
  `530a2a001189c7c0a4dfa486349b77d80ee5031e2a8b4024793405837dc1611e`;
- eligibility URI: `artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/freeze/eligibility_ledger_v1.csv`;
  bytes `56,719`; SHA-256
  `7fdbcb057a0dba9ba1d9462fde86d6af30add5bdbd1e20d39e24cc96fb51554a`;
- frozen config Git path
  `configs/input_and_alignment/gate_s0/freeze_recovery_v1/recovery_v1.json` at
  accepted commit `853f52c8d843fa8c9bc8d79f62e3e24e1eef10c7`; Git blob
  `4a74d9479236e72b9147294bcd753bb9f096eec4`.

The `100-accepted` preflight is metadata-only: it reuses the predecessor's compact
attestation and checks regular-file type and exact size without opening or hashing
scientific payload bytes. Before the executor's first grid open, it must fsync an
immutable source-open intent. It then reads the 3,023,643 grid bytes exactly once,
computes the declared digest from that same byte stream and parses from memory; it
must not perform a separate grid hash pass. The checkpoint and eligibility compact
records are each read/verified once. The Git config is bound by the accepted commit
and blob before use.

Each completed stage publishes an add-once output and fsync checkpoint before the
next stage. The configured maximum is two attempts (one retry) per incomplete stage.
A crash before a stage checkpoint may reread only that stage's exact compact input
after recording attempt 02; a valid completed checkpoint must be reused without
reopening its input. Actual attempts, reads, digest passes, recovered pending files
and unknown crash-boundary bytes must be reported.

The task must not reopen or hash the 1.28 GB raw UAS LAZ, the four common-base
consumers, ALS tiles, C5 JSONL sources, R1 15.7 GB inputs, `Images.zip`, `OPF.zip`,
source LoD2, context-only `scene.mvs`, protected held-out outcomes or any prior
performance result. If the compact grid is insufficient, the task returns an exact
blocker; it does not expand authority to raw-source replay.

All new outputs are add-once in a new external task namespace. No predecessor
artifact, packet, Return or receipt may be edited, deleted, renamed or overwritten.

## Baseline attrition to reproduce from compact bytes

The first step must reproduce these outcome-free counts without reading raw UAS:

| Cumulative independent-UAS rule | buildings with >=4 score cells |
|---|---:|
| raw observed compact-grid cells | 129 |
| >=3 points/cell | 129 |
| >=2.5 m above UAS-derived terrain | 124 |
| within-cell Z standard deviation <=0.60 m | 124 |
| local valid neighbours >=6 | 124 |
| local-plane RMSE <=0.30 m | 96 |
| normal up-dot >=0.5 | 96 |
| fixed roughness rejection | 94 |
| preliminary component >=20 cells | 89 |
| preliminary-component planar fraction >=0.70 | 12 |
| final planar component >=20 cells | 10 |

The current final reference has four components, 1,184 cells and 11 intersecting
canonical buildings; one building has only two score cells and therefore fails the
fixed minimum of four.

## One diagnostic alternative, not an adopted rule

Removing only the preliminary-component planar-fraction gate while retaining every
per-cell rule and final 20-cell connected-component rule produced, in read-only
diagnosis:

- 143 final components and 21,079 cells;
- 72 buildings with at least four independent-UAS score cells;
- all 72 also satisfying existing image/MVS/C4/C5 availability;
- 19,895 added cells, or 94.4% of the alternative reference, from preliminary
  elevated components whose planar share was below 0.70;
- 44 fixed-50 m tile-only groups, but at most nine groups with sizes
  `47, 7, 5, 5, 4, 1, 1, 1, 1` after shared UAS-component transitive grouping and
  without any C5 geometry grouping;
- 135 of 143 patches intersecting at least one eligible bbox, 76 intersecting more
  than one of the 72 eligible buildings, and one patch intersecting eight buildings.

These numbers prove recoverable local planar support exists, but they do not prove
roof identity or split independence. The alternative remains `DIAGNOSTIC_ONLY`.
It cannot be selected because it raises `E_paired`, and it cannot be passed directly
to P2. Tile-only grouping would leak shared reference patches across splits, while
the required transitive grouping exposes the current 47-building dependence cluster.

## Proposed bounded calibration

An activated revision of this packet may implement only the following sequence:

1. Reproduce the baseline and diagnostic counts from the exact compact grid.
2. Replace the logically misplaced *preliminary-object* purity test with one frozen,
   locally bounded planar-patch segmentation proposal. Its graph/segmentation rules,
   thresholds and tie handling must be specified before the candidate count is
   computed. No threshold sweep or count-target optimization is allowed.
3. Preserve all existing per-cell height, density, Z-spread, neighbourhood,
   least-squares plane, up-normal and roughness guards. Any changed guard is a
   blocker requiring a new DRAFT.
4. Freeze scene-wide UAS-only candidate cells and patch IDs before loading the
   canonical candidate crosswalk or C5 metadata. Candidate bboxes may clip frozen
   score support during evaluation association; they may not create or tune the UAS
   mask.
5. Produce outcome-free contamination diagnostics for every patch: cells, area,
   bbox/diameter, height range, local-plane RMSE, normal/height discontinuity,
   preliminary-source purity and multi-building association. No LoD2 roof geometry,
   ALS, MVS roof or method result may label a patch as correct.
6. Recompute the full grouping graph using fixed 50 m spatial tiles and shared
   frozen UAS patches. The compact C5 inventory proves a one-to-one exact stable-ID
   prior set (199 unique IDs, no duplicate prior), so it creates no cross-building
   shared lineage edge. Do not reuse the old four-component C5-overlap diagnostic
   for new patches and do not reopen C5 geometry. Report group sizes and proposed
   development/validation/held-out counts without opening any outcome.
7. Apply the following prospective paired-binary claim-scope rule, committed before
   the new candidate count is computed. Confirmatory primary generalization uses
   only the P4 held-out split; development and validation buildings never contribute
   to its power. A separate all-`E_paired` table is descriptive/census scope only.
   The two primary contrasts are C4-vs-C3 and C5-vs-C3; family-wise two-sided alpha
   is 0.05 with conservative Bonferroni alpha 0.025 per contrast, desired power is
   0.80, and the planning discordant-pair rate is 0.30 with 0.20/0.40 sensitivity.
   For net PASS transition `delta` and discordance `q`, use
   `ceil(((z_(1-alpha/2)*sqrt(q) + z_power*sqrt(q-delta^2))/delta)^2)`.
   This gives unclustered minima 125 pairs for `delta=0.15` and 69 for
   `delta=0.20` at `q=0.30`.
8. Compute cluster-effective size separately for held-out and for the descriptive
   all-eligible census as `n_eff = n / DE`, where
   `DE = 1 + (sum(m_g^2)/sum(m_g) - 1)*rho`, using shared-patch/spatial group sizes,
   primary `rho=0.05`, and `rho=0/0.10` sensitivity. Freeze one exhaustive group
   split with at least 30 independent groups overall, at least 18 development,
   six validation and six held-out groups. No largest group may exceed 10% of all
   `E_paired` or 20% of held-out membership. These are claim-support checks, not
   patch-selection objectives.
9. Assign exactly one outcome-free scope status:
   - `CONFIRMATORY_MAIN_CLAIM_CANDIDATE` only when held-out `n_eff>=125` at
     `rho=0.05` and every full/held-out group criterion passes;
   - `CONFIRMATORY_LARGE_EFFECT_ONLY_CANDIDATE` when held-out `69<=n_eff<125` and
     every full/held-out group criterion passes, limiting powered confirmatory
     interpretation to effects of about 20 percentage points or larger under the
     declared assumptions;
   - `DESCRIPTIVE_CENSUS_ONLY` when held-out is below 69 but all-eligible
     `n_eff>=69` and the overall group criteria pass; this status permits no
     confirmatory population/generalization claim;
   - `PILOT_ONLY_REFERENCE_SCOPE` otherwise.
   Always report the full `q`/`rho` sensitivity table. No observed method effect may
   enter the calculation or alter these thresholds.
10. Return either one exact reference/split candidate for human Gate review or
   `BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE`. Do not make a scientific verdict or
   authorize performance.

## Acceptance checks

Technical candidate status requires all of the following:

- baseline counts and compact input digests reproduce exactly;
- reference construction uses only the exact checkpointed `c1_grid_v1.npz` and
  frozen config; raw UAS LAZ/XYZ access is prohibited; construction completes before
  candidate association;
- no prohibited input or held-out/performance access;
- every retained cell passes the unchanged per-cell guards;
- deterministic patch IDs and byte-identical replay in the pinned project image;
- complete patch contamination ledger with no hidden removal;
- exact `U_target -> E_paired` inclusion/exclusion ledger and the fixed-tile/shared-
  UAS-patch grouping graph;
- exact compliance or noncompliance with the precommitted full-set and held-out
  group-count, largest-group, cluster-effective-size and claim-scope rules above;
- prospective precision/power sensitivity showing exactly which claim scope the
  achieved set can and cannot support;
- three independent reviews covering scientific isolation, component/group QA and
  reproducibility/read accounting;
- `gate_decision: null` and `scientific_verdict: null` throughout.

An increased building count alone is not an acceptance criterion. If contamination
cannot be bounded without an independent label source, the honest result is a
blocker or a pilot-only scope recommendation.

## Orthogonal blockers and receipt correction

The predecessor Roofer synthetic smoke remains blocked by a non-writable container
working directory. It is outside this reference-calibration task and must not be
rerun here. A later bounded runtime task may mount a task-owned writable working
directory and reuse the synthetic inputs without scientific-source replay.

The predecessor technical failure was closed through `200-verified.json` even though
the canonical `docs/research/05_HANDOFF_PROTOCOL.md` requires `200-blocked.json` for
a technical failure. The hashes, direct-child ancestry, `300-closed` event and writer
return remain recorded, but the event-state meaning is incorrect. Those immutable
receipts must not be changed. Any activated handoff under this packet must cite the
classification defect in its 000/100 events and use:

- `200-verified.json` when the declared procedure, checkpoint, schema, compact-output
  and QA generation complete correctly, including when the scientific scope output
  is `PILOT_ONLY_REFERENCE_SCOPE` or `BLOCKED_REFERENCE_COVERAGE_OR_INDEPENDENCE`;
- `200-blocked.json` only for a technical failure such as runtime, checkpoint,
  schema, missing-output or reproducibility failure;
- a direct-child `300-closed.json` in either case to return writer ownership.

## Required implementation and review before activation

This file is a DRAFT only. Before any 000-offered event or Experiment Host access, a
Work Host implementation commit must add a new config, deterministic compact-grid
runner, tests, output-path contract and crash/no-repeat ledger in new task-owned
paths. Three independent reviews must approve the committed implementation and this
packet must be activated in a separate commit. Past packets and receipts remain
protected.
