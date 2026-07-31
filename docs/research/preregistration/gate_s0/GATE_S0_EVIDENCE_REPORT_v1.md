# Gate S0 Evidence Report v1

- handoff_id: `P2-W2C-GATE-S0-PREP-v1`
- task_id: `P2-GATE-S0-EVIDENCE-PREP-v1`
- input_commit: `9197de13725e6caef8b71887096eeeaf8c3f1da8`
- evidence_time: `2026-07-31T20:12:21+09:00`
- proposed_status: `BLOCKED_FOR_GATE_S0_REVIEW`
- artifact_verification_level: `artifact_verified`
- scientific_verdict: null

## Answer-first status

The Gate S0 evidence package is technically complete but is **not freeze-ready**.
The proposed review status is `BLOCKED_FOR_GATE_S0_REVIEW`, not a scientific or
phase verdict. Exact live bytes were verified for 11 target files totaling
15,743,666,051 bytes, and the 962-image/937-pose discrepancy is now resolved as
an auditable ledger. However, an independent LoD1 was not found, so C5 remains
`MISSING`. C1, C2 and C4 still have coordinate, lineage, classification,
registration or coverage gaps. `U_target`, `E_paired`, split membership and a
defensible per-condition cost ceiling therefore remain unfrozen.

No C1–C5 performance baseline, GS training, prior loss, final adapter or
threshold was run or inspected. No held-out building, protected Fusion W1
payload or external `R_ext` was opened. `scientific_verdict` remains null.

## Exact artifact verification

- Canonical root: `file:/artifacts/JointBuildGS`
- Method: full SHA-256 rehash of the 11 exact target files; no directory-wide hash
- Docker image: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- Files: Images.zip, OPF, two Current UAS LiDAR candidates, Pix4D MVS,
  four Existing ALS tiles and two score-only LoD2 reference tiles
- Image member verification: all 962 JPEG members were individually decompressed
  and hashed into `gate_s0_image_member_inventory_v1.csv`
- Receipt-compatible records:
  `artifacts/manifests/gate_s0/gate_s0_live_artifact_records_v1.json`

`artifact_verified` describes byte verification, not scientific readiness. All
condition-facing assets remain `PARTIAL`, `MISSING` or `UNKNOWN` where CRS,
datum, lineage, role, registration or coverage is incomplete.

## 962/937 deterministic ledger

The image archive has 962 unique JPEG basenames. OPF `camera_list`,
`input_cameras` and `projected_input_cameras` each contain the same 962 camera
IDs/basenames. OPF `calibrated_cameras` contains 937 optimized pose records.
Exactly 25 image/camera IDs have raw input and projected records but no optimized
calibrated-camera pose.

- Ledger rows: 962
- Included: 937
- Excluded: 25
- Exclusion reason: `NO_CALIBRATED_CAMERA_POSE_IN_OPF`
- Ledger SHA-256:
  `8c1e89040869e800c34ebd8a06c2b5185524330fc5d56e594b41686173c465b0`
- Join rule: exact basename; normalize only `Images/` versus `images/` directory case
- Time strings are not used as join keys because filename and OPF timestamps differ
  by one hour.

The proposed common C2–C5 image/camera base is the 937 included IDs. Existing
Pix4D MVS is only `PARTIAL` for same-base proof: its header records
`Pix4Dmatic_1.58.1`, but no producer/replay receipt binds the MVS hash to the
Images.zip hash, OPF hash and exact 937 IDs. Until that receipt or a replay exists,
C2 must be labelled a sensor-processing-bundle baseline and C2-vs-C3 must not be
presented as a method-only contrast.

## C1 — Current UAS/Drone LiDAR

`LIDAR_UAS_CURRENT_NADIR` is proposed provisionally as `NADIR_ONLY` for Gate
review. This choice is outcome-free: numeric header-bbox screening in the two
declared but not yet registered UTM32 frames supports nadir over manual while
avoiding an unvalidated merge. It does not prove exact AOI coverage. Exact
coverage and source freeze remain blocked until the EPSG:32632-to-EPSG:25832
transform/residual and per-building coverage are verified.

The source is still `PARTIAL`:

- exact nadir bytes and SHA-256 are verified;
- header horizontal evidence is EPSG:32632, but vertical datum is `UNKNOWN`;
- a fixed first/middle/last 750,000-point sample contains raw class 0 only;
- the low Z minimum needs a frozen outlier rule;
- no EPSG:25832/DHHN2016 transformation or registration residual is frozen;
- no provenance-bound ground=2/building=6 derivative exists;
- per-building class-specific coverage is unavailable.

The config records the required non-GT conversion sequence without inventing
parameters. No C1 point cloud was modified or generated.

## C2 — Current-image MVS

The Pix4D MVS file is live and byte-verified. Its header contains 395,312,667
points and `Pix4Dmatic_1.58.1`, with EPSG:32632 plus prior EGM96/EPSG:5773
evidence. Its numeric XY extent comparison is provisional because the candidate
AOI is EPSG:25832; exact coverage is not established. It remains `PARTIAL`
because:

- exact derivation from the proposed 937 image/pose set is not hash-bound;
- the bounded class sample contains class 0 only;
- the class-2/6 Roofer derivative is missing;
- EPSG:25832/DHHN2016 transformation and residual are not frozen;
- per-building coverage is not available.

Dense MVS geometry, depth and normals remain prohibited from C3–C5.

## C4 — Existing ALS prior

Four 2022 ALS tiles are exact-byte verified. Their bounded samples contain
ground/building and provider-specific classes and their density is about
20.18–22.80 points/m² by gross 1 km² tile bounds. They are distinct files and a
different survey regime from the 2024 UAS C1 candidate. This supports asset-role
separation but does not finish independence.

The proposed future interface is limited to XYZ, classification, intensity,
tile/source identity, coverage and input-quality confidence. It defines no loss
equation or weight. C4 remains `PARTIAL/UNKNOWN` until provider/header CRS and
datum evidence, derivative independence, EPSG:25832/DHHN2016 registration
residual, building overlap and confidence semantics are bound. Existing ALS is
not C1, reference or ground truth.

C4/C5 complementarity is reserved for later rescue-set and failure-mode
comparison. This package makes no joint-prior synergy claim.

## C5 — Independent LoD1

No independent LoD1 was found in the fixed approved raw-input search scope.
The deterministic evidence records the root, maximum depth, filename/suffix
rules, sorted regular-file name/size inventory hash and candidate matches without
opening model geometry. Only the two score-only LoD2 GML files matched the model
suffix inventory; neither filename is a LoD1 match. C5 is therefore `MISSING`
within that declared scope.

The scored LoD2 is not simplified, extruded or converted into LoD1. LoD2 Z,
`RoofSurface`, roof type, semantic labels and final models remain prohibited
from honest-arm inputs. This is the decisive Gate S0 blocker.

## Outcome-free AOI and eligibility funnel

The candidate rectangle is EPSG:25832 X 690791.740–691154.650, Y
5335864.050–5336353.850, area 177,753.318 m². It is proposed from previously
audited scene coverage and is not frozen. The reported 199 intersections are a
provisional score-reference coverage count, not `U_target` or `E_paired`.

No building IDs were fabricated or assigned to development, validation or
held-out. `U_target` remains `UNKNOWN` because a stable-ID plus current-image
coverage join is absent. C1–C4 building-level eligibility remains `UNKNOWN`, C5
is `MISSING`, and `E_paired` cannot be computed safely. All funnel rows retain
explicit reasons and `held_out_accessed=false`.

## Cost evidence

Exact known input bytes are recorded per condition, but runtime, peak memory,
output bytes and retention ceilings remain `UNKNOWN`. There is no comparable,
non-held-out calibration receipt for the new C1–C5 program, and running a
performance baseline was outside scope. Historical capability runs were not
opened or extrapolated per building. Gate S0 cannot freeze exhaustive versus
sampled execution until a separately authorized bounded calibration supplies
these values.

## Split proposal

`EXHAUSTIVE_PARTITION` remains the preferred mode. The machine proposal fixes a
deterministic group-order algorithm and an outcome-free seed, but all ID lists
are empty because `U_target` and `E_paired` are not frozen. Multipart/source
groups and spatially adjacent groups must remain together. Roof type, LoD2
`RoofSurface`, semantic evaluation labels and method results are prohibited
strata.

`STRATIFIED_SAMPLE` is only a fallback if a frozen cost ceiling proves
exhaustive execution infeasible and the user separately approves it. P2 and P3
must use the same development+validation pool; P4 first opens every frozen
held-out building for C1–C5.

## R_derived, gravity and writer readiness

- `R_derived`: `PARTIAL`; the common non-GT campaign code/config and
  method-specific polygon hashes do not yet exist.
- Gravity: `UNKNOWN`; it must be estimated once from terrain MVS normals and
  bound by vector/source/hash. It is not hardcoded here.
- CityJSON: `PARTIAL`; the repository writer compiles and `cjio 0.10.1` is
  present.
- Roofer, val3dity, cjval, ogr2ogr and PDAL: missing from the main live image.
- CityGML: `MISSING`; no trusted provenance-bound converter/serializer and cjval
  path is available.
- G0–G4 writer: definitions exist, but no integrated C1–C5 writer/evaluator is
  ready. No G3/G4 numerical threshold, final adapter, fallback acceptance or
  `PASS_usable` verdict is set.

## Gate S0 review blockers

1. C5 independent LoD1 is `MISSING`.
2. C1 class-2/6 derivative, vertical datum, transform, residual and per-building
   coverage are missing or unknown.
3. C2 exact same-base derivation, class-2/6 derivative, transform and coverage
   are incomplete.
4. C4 derivative independence, registration, overlap and confidence semantics
   are incomplete.
5. Common `R_derived`, gravity, `U_target`, `E_paired` and split IDs are not
   frozen.
6. Runtime, memory, output-byte and retention ceilings are unknown.
7. Integrated Roofer/CityJSON/CityGML/cjval/val3dity and G0–G4 writer readiness
   is incomplete.

## Recommended next evidence action

Work Host should review this blocked evidence package and prepare a new,
authorized remediation packet for missing input provenance and bounded
non-held-out calibration. The next packet should not start P2 performance runs.
Gate S0 may be reconsidered only after C5 is backed by an independent LoD1 and
the other blockers have exact receipts. The human reviewer retains the Gate S0
and scientific decisions.
