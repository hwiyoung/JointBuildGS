# P2 Gate S0 freeze recovery v1 — DRAFT

- task_id: `P2-GATE-S0-FREEZE-RECOVERY-v1`
- handoff_id: `P2-W2C-GATE-S0-FREEZE-RECOVERY-v1`
- status: `DRAFT_NOT_EXECUTION_AUTHORITY`
- predecessor_closed_commit: `073bda57571acf945c58e566f0c5a5e9c395983f`
- draft_commit: `SELF_AFTER_DRAFT_COMMIT`
- gate_decision: `null`
- scientific_verdict: `null`

## Plain objective

Finish the evidence that the interrupted integrated-freeze task failed to persist.
This is one recovery task, not another exploratory R2 series and not a performance
run. It must leave exactly one of two outcomes: a technically complete Gate S0 draft
for human decision, or one concrete evidence-backed blocker.

## Why recovery is necessary

The predecessor read and hashed exactly four retained paths/eight files/
986,484,109 bytes, and computed gravity while streaming the dense PLY. It then failed
on the already-known absence of `pyproj` when `laspy.header.parse_crs()` opened the C1
header. The runner kept all four digests and gravity only in process memory and wrote
their manifests after C1, C4, reference and eligibility work. The exception therefore
discarded completed upstream evidence.

The failed namespace and its packet, Return, receipts and evidence are immutable. The
four digest values cannot be recovered from Git, stdout or prior attestations. If exact
payload identity remains required, one explicitly recorded second and final pass is
unavoidable. This packet permits that bounded exception only after the safeguards
below are implemented and committed.

## Activation prerequisites

Before this DRAFT can be activated:

1. The complete runner, config, schemas and tests must be committed on Work Host.
   Experiment Host may execute only those exact Git blobs; it must not run WIP source.
2. Docker preflight must pass without reading scientific payload content:
   imports, LAS/LAZ synthetic header and chunk paths, missing-`pyproj` fallback,
   EPSG:32632-to-25832 transform checks, write permissions and a new empty namespace.
3. The runner must split retained fingerprinting from C1/C4/reference processing.
   Each retained file/member digest and the dense-Ply gravity result must be persisted
   with add-once write, flush and fsync immediately after that stage completes.
4. Reuse must validate the full operation identity, committed runner/config blobs and
   checkpoint chain before skipping a completed path.
5. Independent reviews must approve the leakage guard, read accounting and the
   outcome-free universe/registration proposal before offered handoff.

## Frozen inputs and bounded access

### Reused without rehash

- exact common source `B_CURRENT_CANDIDATE_c205892c390997b5`: 962 image members,
  937 calibrated image/pose pairs and 25 no-pose exclusions;
- R1 15.7 GB input attestation, `Images.zip`, `OPF.zip`, C1/C4 raw-input SHA-256
  attestations and R2A output attestations;
- the failed integrated namespace and all past namespaces: metadata evidence only,
  no content recovery read.

### One second-and-final fingerprint pass

Only these retained paths may be hashed, once each, with an exact aggregate ceiling
of 986,484,109 bytes:

- `phase-payloads/p0-audit/data/work/mvs/colmap_dense/sparse`
- `phase-payloads/p0-audit/data/work/mvs/openmvs/scene.mvs`
- `phase-payloads/p0-audit/data/work/mvs/openmvs/dim_dense.ply`
- `phase-payloads/p0-audit/data/work/mvs/dim/dim_v1.laz`

`dim_dense.ply` processing and terrain-normal gravity estimation occur in the same
stream as its fingerprint. No stereo-tree enumeration is permitted.

### Processing-only input passes

- C1: `LIDAR_UAS_CURRENT_NADIR`, one decode pass, no full-input rehash;
- C4: exact 2022 ALS tiles `690_5335`, `690_5336`, `691_5335`, `691_5336`, one decode
  pass each, no full-input rehash;
- C5: the two selected R2A LoD1-prism JSONL outputs, at most one processing pass each,
  prior digest attestation reused; source LoD2 geometry assets remain prohibited.

## Scientific isolation and proposed technical freeze

These are proposed execution rules for a human-review Gate packet, not a scientific
verdict.

1. The current nadir UAS LiDAR is the independent score-only geometry/structure
   reference for C2–C5. C1 remains `SELF_REFERENCE_UPPER_BASELINE`.
2. Independent UAS reference geometry and its digest are constructed and frozen over
   the whole AOI before any C5 LoD1 record is opened.
3. Primary reference components receive deterministic `UASREF_*` IDs derived only
   from frozen UAS-reference geometry. The earlier 199 LoD2-reference intersections
   remain a diagnostic crosswalk and are not forced to be the primary universe.
4. After reference freeze, the LoD2-derived coarse LoD1 may be spatially associated
   to UASREF components only to record C5 input availability and arm-specific prior
   IDs. It may not construct, crop, register, tune, stop, alter or score the reference.
5. `U_target` is the outcome-free UASREF population in the frozen AOI with the frozen
   minimum current-image view support. `E_paired` is its all-condition input/reference
   coverage intersection, computed before any method outcome.
6. Horizontal coordinates use the frozen EPSG:32632-to-25832 transform. C1 is the
   working vertical frame; MVS and ALS may receive only a pre-result terrain
   lower-envelope median Z translation. Absolute vertical-datum equivalence is not
   claimed. Absolute-Z metrics remain disabled unless a separate datum is proven;
   relative/terrain-normalized metrics and limitations are recorded for human review.
7. Components remain: SfM sparse ON, dense MVS ON, gravity ON; depth, normal-map
   supervision, confidence and segmentation OFF.
8. LoD2-derived LoD1 provenance remains explicit. It is never evaluated against its
   source LoD2 lineage, and prior RoofSurface topology, slope, ridge, roof type and
   semantic labels remain excluded.

The activation commit must freeze the exact non-GT UAS building/reference extraction
rule, uncertainty fields, association rule, minimum support thresholds and split
algorithm before Experiment Host access. No threshold may be selected from C1–C5
outcomes or protected held-out results.

## Required execution stages

### Stage A — zero-payload preflight

- verify exact committed runner/config/test blobs and Docker image identity;
- run dependency, synthetic LAS/LAZ, fallback, transform, checkpoint-crash and
  prohibited-path tests;
- verify the new artifact namespace is absent and the failed namespace is untouched.

### Stage B — retained fingerprint checkpoint chain

- fingerprint each selected member/path in fixed order;
- persist and fsync each result immediately;
- compute MVS support grid and gravity in the dense-Ply stream and persist both before
  advancing;
- write a completed fingerprint ledger before any C1 access.

### Stage C — independent reference and registration

- decode C1 once, write the class-2/6 derivative and whole-AOI reference before ID
  association, and persist their same-stream digests;
- decode the four C4 tiles once and persist the derivative;
- record horizontal checks and terrain-only MVS/C4-to-C1 Z translations, residuals,
  working-frame limitation and gravity.

### Stage D — universe, eligibility and split

- freeze UASREF geometry and IDs first;
- perform C5-prior association only after that freeze;
- calculate exact current-image, C1, common-MVS, C4, C5 and independent-reference
  coverage without method outcomes;
- emit exact `U_target`, `E_paired`, exclusions and deterministic exhaustive spatial
  groups/splits with `held_out_accessed=false`.

### Stage E — common Stage 3 and final Gate draft

- verify the common non-GT `R_derived` interface for all C1–C5 labels and external
  roofprint rejection;
- bind the exact Roofer 1.0.0 digest and record runtime availability honestly; no
  building quality comparison is allowed;
- retain the existing hard caps: one RTX-3090-class GPU, 24 GB VRAM, 12 hours/run,
  100 GB/run, one retry and 500 GB total retained output;
- produce a revised Gate S0 human-review draft with READY/PARTIAL/MISSING states.

## Prohibited work

- C1–C5 performance, GS training, held-out access, Fusion W1, `R_ext`, quality scoring
  or threshold selection;
- new SfM/MVS/depth/normal/confidence/segmentation generation;
- any read/hash of R1 15.7 GB inputs, `Images.zip`, `OPF.zip`, stereo, source LoD2
  geometry or failed-namespace payload;
- modifying any prior packet, Return, receipt, canon decision or evidence artifact;
- overwriting, moving or deleting scientific payloads;
- treating a technical receipt or this task as human Gate approval.

## Verification and return

Use Docker-based tests and three independent reviews: scientific leakage/reference
independence, artifact/checkpoint/read accounting, and universe/split/Stage-3 scope.
Record exact input/output paths, Git blobs, Docker identities, byte counts, pass counts,
checkpoint state and failures. Use immutable 000/100/200/300 receipts. `300-closed`
must not reread external artifacts and must return writer ownership to Work Host.

## Done when

- the retained fingerprint and gravity survive any later-stage failure without reread;
- the independent UAS reference, C1/C4 derivatives, registration, `U_target`,
  `E_paired`, exclusions and exact split have durable evidence, or one exact blocker is
  identified;
- the next action is one human Gate S0 decision if technically ready, otherwise one
  concrete bounded blocker;
- `gate_decision` and `scientific_verdict` remain `null`.

