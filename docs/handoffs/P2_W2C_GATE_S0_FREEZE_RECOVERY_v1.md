# P2 Gate S0 freeze recovery v1 — bounded technical execution authority

- task_id: `P2-GATE-S0-FREEZE-RECOVERY-v1`
- handoff_id: `P2-W2C-GATE-S0-FREEZE-RECOVERY-v1`
- status: `AUTHORIZED_BOUNDED_TECHNICAL_EXECUTION`
- predecessor_closed_commit: `073bda57571acf945c58e566f0c5a5e9c395983f`
- draft_commit: `4ce6de11a2677e3e068df9b9ad2039e0e6cbe50d`
- implementation_commit: `1687432a586a5a924e17e556860171bc83e64cad`
- gate_decision: `null`
- scientific_verdict: `null`

## Objective

Close the remaining Gate S0 input, target, eligibility, split, reference and
toolchain evidence in one bounded technical task. This is interruption recovery,
not another exploratory R2 task and not a performance run. It must finish with
either a technically complete human-review Gate draft or one exact blocker.

## Predecessor failure and correction

The predecessor read four retained paths/eight files/986,484,109 bytes and derived
gravity, then failed on the already-known absence of `pyproj` before persisting the
in-memory results. The scientific inputs were not missing; the runner incorrectly
made completed upstream evidence depend on all later stages.

This recovery does not repeat the predecessor's four-path archival fingerprint.
It separates producer-lineage evidence from the actual consumer graph and reads only
the four files consumed by the first-wave adapter. Every completed stage is add-once and
fsync-persisted before the next scientific source is opened. The failed namespace and
all predecessor records remain immutable.

## Activation evidence and transfer prerequisite

This packet is technical execution authority because:

1. Runner, config, host orchestrator and tests are committed at
   `1687432a586a5a924e17e556860171bc83e64cad`. Experiment Host may execute only blobs
   bound by the offered commit and must not patch-and-run WIP source.
2. A zero-scientific-payload Docker preflight passed for that implementation and verifies imports, synthetic LAS/LAZ,
   missing-`pyproj` fallback, EPSG transform, checkpoint crash semantics, clean Git
   state, exact source blobs and a new namespace.
3. Three independent reviews approved scientific isolation, read/checkpoint
   accounting and the universe/split/Stage-3 contract after all reported blockers
   were corrected. The validated suite contains 39 tests.

Execution still requires an immutable `000-offered` receipt that offers writer
ownership; it does not transfer ownership by itself.

Experiment Host must add one metadata-only acceptance artifact bound by the immutable
`100-accepted` receipt. Only its committed and pushed acceptance activates the writer
transfer. The artifact records the exact physical-host ID,
canonical artifact root and stat-only byte sizes for the eleven authorized consumer
inputs, plus the observed project Docker image ID. `execute` requires
`HEAD == origin/main == 100-accepted commit`, runs the canonical handoff validator and verifies
the accepted receipt, artifact digest and all transitive executable Git blobs before
opening source content.

## Frozen source and minimal consumer graph

Reused without rehash:

- `B_CURRENT_CANDIDATE_c205892c390997b5`: exact 962 image members, 937 calibrated
  image/pose pairs and 25 no-pose exclusions;
- R1 15.7 GB input attestation, `Images.zip`, `OPF.zip`, C1/C4 raw-input attestations,
  R2A output attestations and prior receipt chains;
- R2B producer route and retention metadata;
- all failed/predecessor namespace content.

Read once because the frozen adapter actually consumes them:

- `cameras.bin`, 64 bytes: camera intrinsics;
- `images.bin`, 114,415,526 bytes: exact-937 image poses/names;
- `points3D.bin`, 33,476,840 bytes: frozen SfM sparse initialization for C3–C5;
- `dim_dense.ply`, 659,138,498 bytes: common MVS geometry, controlled C2 derivative,
  MVS terrain and gravity.

The same-pass consumer digest is computed in each processing stream; there is no extra
hash-only pass. The exact common-base read ceiling is 807,030,928 bytes. The following retained producer
intermediates are context-only and are not opened, hashed or called consumer inputs:
`rigs.bin`, `frames.bin`, `scene.mvs`, `dim_v1.laz`, retained images
and the stereo tree. Accordingly, the first-wave component contract is camera/pose
model ON, sparse points ON, dense PLY ON.

Processing-only passes, without input rehash:

- C1/current nadir UAS LiDAR: one decode pass;
- C4/existing 2022 ALS: one decode pass for each exact four tiles;
- C5: one pass for each of the two selected R2A LoD1-prism JSONL outputs;
- source LoD2 geometry: zero access.

## Frozen research scene

The research scene is not selected from method performance, roof type, `RoofSurface`
or evaluation quality. Its exact P0 lineage is: current-image MVS XYZ was classified
with SMRF ground as class 2, while an LoD2 `GroundSurface` footprint overlay marked
non-ground points as class 6; `05_footprints.py` sampled the resulting class-2/6
points, took the X/Y 1st-to-99th percentile extent, and added a fixed 25 m margin.
Therefore LoD2 `GroundSurface` geometry influenced the AOI sample before the rectangle
was fixed. This provenance is disclosed rather than misdescribed as raw-MVS-only.
The frozen EPSG:25832 rectangle is
`[690791.74, 5335864.05, 691154.65, 5336353.85]`, area 177,753.318 m2. Its rule is
implemented in `phases/p0-audit/scripts/05_footprints.py` and the frozen GeoJSON digest
is `93728956ecfbbb24521b4fa4aec745fec176d4c6c94e10cef272934dcf9d9061`.

After this outcome-free AOI was fixed, canonical LoD2 `GroundSurface` stable IDs were
intersected with it, yielding exactly 199 scene-building candidates. This ID-selection
step is later than the AOI, while the class-6 overlay used to construct the AOI sample
is earlier. No `RoofSurface`, roof type, semantic evaluation label or method outcome
was used. Thus 199 is not a manual sample and 12,049 is not the research-scene count:
12,049 is the upstream two-tile source inventory from which C5 LoD1 prisms were
produced.

## Scientific isolation and proposed technical freeze

These rules produce evidence for a later human Gate decision; they are not a
scientific verdict.

1. C2–C5 use an independent, score-only current UAS roof-support reference. C1 is
   explicitly a self-reference upper baseline.
2. The UAS reference is extracted over the fixed AOI using XYZ geometry only: frozen
   one-metre grid, multiscale lower terrain envelope, height >=2.5 m, >=3 points/cell,
   within-cell Z standard deviation <=0.60 m, >=6 valid 5x5 neighbours, actual
   least-squares local-plane RMSE <=0.30 m, up-dot >=0.5, fixed multilayer/roughness
   rejection, component planar fraction >=0.70 and unclosed 8-neighbour components
   of >=20 cells. No RGB, LoD2, ALS,
   MVS, semantic label or method outcome may construct the mask.
3. `UASREF_*` component IDs depend on the UAS attestation, reference-rule/AOI-grid
   identity and sorted XY cell indices, never Z.
   The whole-AOI reference and digest are fsync-frozen before either C5 JSONL is read.
4. LoD2-derived coarse LoD1 is the C5 input prior. Input availability is any prior
   footprint within the fixed 10 m processing buffer; reference overlap and centroid
   match are diagnostic values only and never exclude prior–current conflict cases.
   Association to frozen UASREF units uses footprint XY only. `ground_height_m`, `top_height_m`, roof
   topology, slope, ridge, roof type and semantic labels cannot construct, alter,
   register, crop, tune, stop or score the reference. A reference digest equality
   check is required before and after association. All exact 199 candidate IDs must
   have one and only one retained prior within this buffer; partial C5 coverage is a
   technical blocker, not a READY subset.
5. `U_target` starts from the canonical 199 stable building IDs whose LoD2
   GroundSurface footprints intersect the fixed scene AOI, then requires at least two
   exact-937 camera-frustum supports. The 12,049 source-tile objects are only the
   upstream inventory; they are not the research-scene population.
6. The independently extracted UAS roof components are associated to the 199 stable
   IDs after reference freeze for evaluation only. Only independent UAS cells inside
   the fixed target bbox become per-building score support; buffered-centroid matches
   remain diagnostic. Their geometry, not the LoD2 footprint, is the score reference.
   UAS components are roof-support evidence and
   are not silently re-labelled as cadastral buildings. `E_paired` is `U_target`
   intersected with frozen C1 independent-reference, common-MVS, C4 and exact C5-prior
   availability. Later method failures are G0 outcomes, not exclusions.
7. C3–C5 input registration cannot use UAS roof geometry. C4 and C5 input-side
   vertical alignment uses MVS terrain only. C1/UAS terrain is evaluation-side only.
   Because absolute vertical-datum equivalence is unproven, primary evaluation is
   terrain-normalized/relative and absolute-Z metrics are disabled.
8. Execution groups use AOI-anchored fixed 50 m core tiles plus fixed 10 m processing
   context. An AOI-intersecting target is assigned by the centroid of its target bbox
   clipped to the AOI, so boundary buildings remain among the exact 199 while every
   assigned tile exists in the frozen tile map. Split groups connect units in the same core tile or units sharing an
   independently extracted UAS component/C5 association. The 10 m context does not
   connect every adjacent tile: held-out means held-out buildings, not disjoint source
   images, and treating ordinary overlapping image/point context as label leakage would
   collapse the entire contiguous downtown scene into one unusable group. Whole groups
   are deterministically assigned 60/20/20 using seed `20260731`; all three splits must
   be non-empty and no protected result is read to create the split.
9. Components are camera/pose model ON, sparse points ON, dense MVS ON, gravity ON;
   depth, normal-map supervision, confidence and segmentation OFF.
10. LoD2-derived LoD1 remains `REFERENCE_DERIVED_DIAGNOSTIC_ONLY` with respect to its
    source lineage. It cannot make primary C5 or `E_paired` READY by self-evaluation;
    only the separately frozen UAS reference permits primary evaluation.

This task freezes the data side of evaluation: exact independent reference bytes and
construction rule, canonical target IDs, per-condition attemptability, relative-height
scope, spatial groups and split IDs. It does not invent the final G3/G4 numerical PASS
threshold. Under the canon, P2 uses development and validation buildings to calibrate
those numerical thresholds from C1-C3 baselines and reference uncertainty, then freezes
the criterion before prior-guided held-out evaluation. Therefore a deferred numerical
threshold is planned P2 work, not a reason to keep Gate S0 blocked once this technical
data freeze is accepted.

## Execution stages

1. Zero-payload preflight and exact Git/blob binding.
2. `cameras.bin`, `images.bin`, `points3D.bin` and dense PLY processing; each digest, pose summary,
   MVS grid/derivative and gravity checkpointed before advancing.
3. C1 decode; class-2/6 derivative, UASREF cells/IDs and pre-C5 digest persisted.
4. C4 four-tile decode and MVS-terrain-only input alignment evidence.
5. Load the exact 199-ID evaluation-only crosswalk after reference freeze; process C5
   JSONL once and retain the 199 matching priors, then compute `U_target`, `E_paired`,
   exclusions, exhaustive groups and split.
6. Common non-GT `R_derived` Stage-3 interface checks for all five labels and one
   pinned Roofer runtime smoke. The receipt binds the operation ID, exact synthetic
   input and derived-roofprint digests, observed pinned image, command contract,
   runtime log and parsed CityJSON geometry. An empty JSON object is a failure. This
   is interface/runtime evidence, not quality.
7. Compact manifests, report, Return and immutable 100/200/300 receipt closure.

A retry may resume only from a completed checkpoint whose operation identity,
predecessor digest and compact output digests validate. Camera, pose, dense-MVS, C1,
each C4 tile and each C5 JSONL have separately persisted stage products. Completed
scientific sources are not reopened. A crash inside the currently incomplete stage is
recorded honestly; the contract does not claim zero reread before that stage reached
fsync completion. Writes use same-directory pending files, fsync and atomic no-replace
publication. A published orphan is accepted only when deterministic retry bytes match;
an incomplete pending file is quarantined inside the exact task namespace.
Before every scientific-source open, an immutable attempt record is fsync-persisted.
The final ledger reports actual per-stage attempt counts and unknown crash-boundary
bytes honestly; the configured single retry is enforced per stage.

The only Roofer invocation authority is the committed
`scripts/input_and_alignment/gate_s0/freeze_recovery_v1/run_roofer_smoke_host.sh`.
Before creating an attempt, it validates the 100 receipt, writer/HEAD/origin,
acceptance artifact and Git blobs and verifies that the mutable project tag resolves
to the exact project image ID frozen by acceptance. It then invokes the recorder by
that immutable ID. Roofer itself sees only the two synthetic inputs read-only and its
pending output directory, never the artifact root or scientific inputs. Its output,
log, output files and a temporary exit-code file are fsync-persisted before the
completion marker is atomically published. The attempt directory is then atomically
renamed and the parent directory is synced. An interrupted incomplete
attempt is quarantined and may use the single bounded retry, while a sealed attempt is
recorded without rerunning Roofer. The recorder repeats runtime control and binds the
project and Roofer image IDs. For that stat-only acceptance check it sees the artifact
root read-only, with only the nested task namespace mounted read-write. CityJSON must contain non-empty geometry boundaries and
vertices before checkpoint 110 can complete.

## Prohibited work

- C1–C5 performance, GS training, quality scoring, protected held-out access,
  Fusion W1 or `R_ext`;
- new SfM/MVS/depth/normal/confidence/segmentation generation;
- R1/`Images.zip`/`OPF.zip` rehash, stereo enumeration, source LoD2 access, failed
  namespace reads or non-consumer common-base fingerprinting;
- external/GT roofprints, UAS-reference-based C3–C5 registration or outcome-selected
  thresholds;
- modification of any past packet, Return, receipt, decision or evidence artifact;
- deletion, overwrite or movement of scientific payloads;
- a non-null `scientific_verdict` or implicit human Gate approval.

## Cost and closure

The existing caps remain: one RTX-3090-class GPU, 24 GB VRAM, 12 hours/run, 100
GB/run, one retry and 500 GB total retained output. Three independent reviews cover
scientific leakage/reference independence, checkpoint/read accounting and
universe/split/Stage-3 scope. `300-closed` performs no external artifact reread and
returns writer ownership to Work Host. `gate_decision` and `scientific_verdict`
remain `null`.
