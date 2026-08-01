# Work-to-Codex Task Packet — Gate S0 Integrated Freeze Closure v1

## Handoff metadata

- handoff_id: `P2-W2C-GATE-S0-INTEGRATED-FREEZE-CLOSURE-v1`
- task_id: `P2-GATE-S0-INTEGRATED-FREEZE-CLOSURE-v1`
- phase: `P2 / pre-result Gate S0 integrated technical closure`
- direction: `Work→Codex`
- status: `DRAFT`
- packet_version: `v1`
- source_commit: `TO_BE_BOUND_AFTER_DRAFT_COMMIT`
- target_branch: `main`
- research_charter_version: `C1C5_CANON_v2`
- decision_log_through: `DEC-P1-012`
- follows: `P2-W2C-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1`
- created_at: `2026-08-01`
- user_standing_authorization: `GRANTED — proceed without serial process-for-process tasks; preserve research intent; use independent sub-agent verification; report stage outcomes`
- repository_effective_phase: `C1–C5 PROGRAM / GATE S0 FREEZE DRAFT / PERFORMANCE BLOCKED`
- scientific_verdict: null

This is the one integrated technical closure task. It replaces serial R2C/R2D-style
microtasks. It does not approve Gate S0 and grants no C1–C5 performance authority.

## Answer first

The task binds the already-selected inputs into one pre-result experiment contract:

1. accept the retained exact-937 sparse/dense chain and fingerprint only its four
   selected paths once;
2. freeze the first-wave common components as sparse `ON`, dense MVS `ON`, depth
   `OFF`, normal-map supervision `OFF`, confidence `OFF`, segmentation `OFF`, and
   gravity `ON` from terrain MVS normals once;
3. bind C1 to current nadir UAS LiDAR and C4 to the four exact 2022 ALS tiles;
4. build an evaluation-only geometry/roof-plane reference from current UAS LiDAR,
   independent of the LoD2 used to make the C5 coarse LoD1;
5. freeze the existing outcome-free AOI, compute exact `U_target` and `E_paired`, and
   assign spatial-group splits without reading outcomes;
6. prove the common Stage-3 interface with pinned tools and a synthetic smoke test;
7. publish `GATE_S0_FREEZE_PACKET_v2.md` as a human-review draft.

## Technical choices for this closure task

These choices are execution defaults used to prepare the final human Gate packet.
They are not a scientific verdict.

| Item | Closure choice |
|---|---|
| common source | `B_CURRENT_CANDIDATE_c205892c390997b5`, exact 962/937/25 |
| SfM sparse | retained exact-937 candidate, `ON` |
| dense MVS | retained exact-937 chain, `ON` |
| depth / normal-map supervision | `OFF`; do not recover or regenerate for first wave |
| confidence / segmentation | `OFF`; do not generate for first wave |
| gravity | `ON`; estimate once from selected dense-MVS terrain normals |
| C1 | `LIDAR_UAS_CURRENT_NADIR` only; manual source remains supplemental |
| C4 | `ALS_EXISTING_690_5335`, `690_5336`, `691_5335`, `691_5336` |
| C5 input | R2A LoD2-derived coarse LoD1 selected by `DEC-P1-012` |
| primary evaluation | new current-UAS-LiDAR-derived reference for C2–C5 |
| C1 evaluation class | `SELF_REFERENCE_UPPER_BASELINE`, reported explicitly |
| input LoD2 in evaluation | prohibited for primary C5 scoring/reference construction |
| AOI | EPSG:25832 rectangle, area 177,753.318 m², GeoJSON SHA-256 `93728956ecfbbb24521b4fa4aec745fec176d4c6c94e10cef272934dcf9d9061` |
| target candidate IDs | existing 199 stable-ID candidate set SHA-256 `047717a5d678aeed540602a2d4fc9a57a076e2ac9205b22a4de75315c1622fe5` |
| split | `EXHAUSTIVE_PARTITION`, spatial groups, 60/20/20, seed `20260731` |

The C5 input must be described as **LoD2-derived coarse LoD1 prior, independently
evaluated**, not as an independent existing LoD1. Its source RoofSurface, ridge,
slope, topology, roof type and semantic labels remain prohibited inputs.

## Existing evidence to reuse

- exact source decision `DEC-P1-012` and R1/R2A attestations;
- R2B Git/source crosswalk and retained-path bounded metadata;
- `gate_s0_input_manifest_v1.json` exact source hashes;
- candidate AOI GeoJSON and the 199-ID reference-intersection ledger;
- R1 evaluation-reference, condition-provenance and Stage-3 inventories;
- P0 Roofer/tool versions and compact replay receipts;
- existing LoD1 processing/digest ledger without re-reading its outputs.

Do not full-hash Images.zip, OPF.zip, the R1 15.7 GB input set, the retained stereo
tree, raw C1/C4 inputs already attested, or R2A LoD1 outputs.

## Required execution

### A. Artifact preflight and corrected R2B interpretation

- Resolve and record the exact Experiment Host artifact root before payload access.
- Bind the resolved root, host, executable blob/commit and config hash into each new
  operation identity and immutable receipt.
- Treat the retained producer as `STRONGLY_CORROBORATED_PRODUCER_ROUTE / PARTIAL`,
  not an exact run-script attestation.
- Record the R2B accounting correction: completed lookup reads/hashes the ledger
  itself; only non-ledger outputs and external payloads are zero-read on reuse.
- If a completed ledger is absent but any intended output already exists, stop before
  external access. Count every directory enumeration and byte read/hash.

### B. One-pass retained-chain fingerprint

Hash exactly these selected paths once, with a combined ceiling of
`986,484,109 bytes`:

- `phase-payloads/p0-audit/data/work/mvs/colmap_dense/sparse`
- `phase-payloads/p0-audit/data/work/mvs/openmvs/scene.mvs`
- `phase-payloads/p0-audit/data/work/mvs/openmvs/dim_dense.ply`
- `phase-payloads/p0-audit/data/work/mvs/dim/dim_v1.laz`

For the directory, emit a deterministic member ledger and Merkle/content identity.
Do not read the 22.75 GB stereo tree or regenerate SfM/MVS.

### C. Frame, datum and gravity

- Bind EPSG:32632 source evidence to canonical EPSG:25832 with the exact horizontal
  transform and residual.
- Determine and record the vertical-datum contract; do not silently equate unknown
  heights with DHHN2016.
- Estimate gravity once from terrain normals derived from the selected dense MVS.
  No hard-coded Z-up and no GT/LoD2 normals are allowed.

### D. C1, C4 and independent evaluation reference

- Process the already-attested C1 nadir UAS LiDAR and four C4 ALS tiles only once;
  combine processing and new-output digest in the same stream.
- Produce non-GT class-2/6 derivatives and terrain-only registration residuals.
- Build the evaluation-only reference from current UAS LiDAR without using either
  input LoD2 tile for geometry, registration, cropping, tuning or stopping.
- LoD2 stable IDs may be joined only after reference geometry is frozen and only as
  evaluation identity labels; their coordinates and RoofSurface geometry must not
  alter the reference.
- C1 is an explicitly self-referenced upper baseline. C2–C5 use the same independent
  evaluation reference.

### E. Outcome-free universe and split

- Freeze the existing AOI; do not optimize it from method results.
- For all 199 candidates, join current-image view support, C1 coverage, retained MVS,
  C4 ALS, selected C5 LoD1 and independent-reference coverage.
- Emit exact `U_target`, `E_paired`, per-condition attemptability and every exclusion
  reason before performance access.
- Assign whole spatial groups by SHA-256(seed|group_id), 60/20/20 development,
  validation and held-out. Keep `held_out_accessed=false` and do not open protected
  held-out outputs.

### F. Stage 3 and bounded cost

- Reuse pinned Roofer 1.0.0 and the P0 tools recipe if obtainable by exact digest.
- Implement or bind one common non-GT `R_derived` interface and writer for C1–C5;
  no external roofprint may enter an honest arm.
- Run only synthetic/interface smoke tests, not a building quality comparison.
- Administrative hard caps for later GS runs:
  - one RTX 3090-class GPU per condition run;
  - VRAM at most 24 GB;
  - wall clock at most 12 hours per run;
  - new output at most 100 GB per run;
  - at most one retry;
  - total new retained storage at most 500 GB.

### G. Integrated Gate return

Produce one revised `GATE_S0_FREEZE_PACKET_v2.md` with a simple READY/PARTIAL/MISSING
table, exact manifests and one explicit `READY_FOR_HUMAN_GATE_DECISION` or
`BLOCKED` technical state. Keep `gate_decision` and `scientific_verdict` null.

## Required outputs

- four-path digest/member manifest;
- component enablement manifest;
- frame/datum/registration and gravity receipt;
- C1/C4 derivative manifests;
- independent-reference lineage and leakage guard;
- 199-row eligibility ledger plus exact `U_target` and `E_paired` manifests;
- exact split manifest with `held_out_accessed=false`;
- Stage-3 common-interface manifest and synthetic smoke receipt;
- administrative cost-cap manifest;
- R2B corrections/addendum without modifying R2B files;
- `docs/research/preregistration/gate_s0/GATE_S0_FREEZE_PACKET_v2.md`;
- Return Packet with `scientific_verdict: null`.

## Proposed Git write scope after activation

- `artifacts/manifests/handoffs/P2-W2C-GATE-S0-INTEGRATED-FREEZE-CLOSURE-v1`
- `artifacts/manifests/gate_s0/integrated_freeze_closure_v1`
- `configs/input_and_alignment/gate_s0/integrated_freeze_closure_v1`
- `configs/stage3/gate_s0_integrated_v1`
- `docs/handoffs/returns/P2_C2W_GATE_S0_INTEGRATED_FREEZE_CLOSURE_v1.md`
- `docs/research/preregistration/gate_s0/integrated_freeze_closure_v1`
- `docs/research/preregistration/gate_s0/GATE_S0_FREEZE_PACKET_v2.md`
- `scripts/input_and_alignment/gate_s0/integrated_freeze_closure_v1`
- `src/stage3/gate_s0_integrated_v1`
- `tests/input_and_alignment/gate_s0/integrated_freeze_closure_v1`
- `tests/stage3/gate_s0_integrated_v1`

All past packets, returns, receipts, R1/R2A/R2B evidence, research canon, held-out,
Fusion W1 and performance outputs are protected.

## Prohibited work

- C1–C5 performance, GS training, quality scoring or threshold selection;
- held-out, Fusion W1 or `R_ext` access;
- new SfM/dense MVS/depth/normal/confidence/segmentation generation;
- full rehash of previously attested large inputs or retained stereo payloads;
- modifying past packet/return/receipt/evidence files;
- using input LoD2 geometry to construct the independent reference;
- primary C5 promotion, Gate approval or non-null scientific verdict;
- overwriting, moving or deleting existing scientific payloads.

## Verification and no-repeat contract

- Docker-based execution and unit/integration tests;
- explicit resolved artifact root and exact input attestation in 100/200 receipts;
- first-pass read/hash counters for every operation;
- exact second invocation: ledger lookup bytes reported honestly, external scientific
  payload and non-ledger outputs read/hash `0`, writes `0`;
- partial-output-without-ledger conflict blocks before external access;
- protected-scope and no-performance/no-held-out tests;
- artifact-verified 200 receipt and direct-child 300 close returning writer to Work
  Host; 300 must not re-read external payload.

## Stop conditions

Continue through independent components and report partial results rather than
stopping at the first non-destructive gap. Stop the whole task only for:

- source/member contradiction with exact 962/937/25;
- a required protected payload rehash outside the stated byte budget;
- input LoD2 leakage into the independent reference;
- overwrite/move/delete risk;
- writer/remote/scope ambiguity;
- performance or protected held-out access requirement.

## Done when

- all sections A–G have a result or an explicit evidence-backed blocker;
- no serial follow-up task is proposed for items that can be decided `OFF` or bounded
  administratively;
- the next action is exactly one human Gate S0 decision if technically ready, or one
  concrete blocker if not;
- `scientific_verdict` remains null and writer ownership is returned.
