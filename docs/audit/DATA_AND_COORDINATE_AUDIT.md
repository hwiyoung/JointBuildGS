# P1 Data and Coordinate Audit

- audited checkout: `130ff958ddaf33b663065dfb2dfa593645776fa2`
- canonical container root: `/artifacts/JointBuildGS`
- host resolver: sibling `../JointBuildGS-artifacts`
- inspection time: `2026-07-31T16:50:24+09:00`
- access mode: read-only, exact-target verification only
- scientific_verdict: null

No directory-wide hash was computed for the approximately 428 GB artifact
store. The following exact candidates were rehashed and inspected because they
are plausible P1/P2 inputs or required pilot evidence.

## Exact live object inventory

All paths below are relative to `/artifacts/JointBuildGS`.

| Asset/role | Relative path | Bytes | SHA-256 | Status |
|---|---|---:|---|---|
| Current imagery archive | `phase-payloads/p0-audit/data/raw/uav/Images.zip` | 5,906,891,973 | `078056d16c8ed7e75d5f22206fdb635327a1ed80e5a4e5890930ba17a43fb34d` | READY |
| OPF/camera archive | `phase-payloads/p0-audit/data/raw/uav/opf.zip` | 1,936,493,976 | `ae83a054cf2f338874ff7bac7b3e17895b8e4405d429674790da3801a0352daa` | READY |
| Current UAS LiDAR manual | `phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_manual.laz` | 1,582,058,159 | `e38aecd5c6a103c037a573513beabefe7a5c8d984e0ecf407a1a43fa8e778f01` | PARTIAL |
| Current UAS LiDAR nadir | `phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_ULS_20241217_nadir.laz` | 1,277,996,022 | `50783bfb205ea5532ac2a300d7e41b6b6426e45009d6c961d603e079cc5ae7b4` | PARTIAL |
| Pix4D MVS point cloud | `phase-payloads/p0-audit/data/raw/tum2twin/TUM_Downtown_Photogrammetry_20241217.laz` | 4,264,934,724 | `fa6826d717d9501972e86b662cb980953a14360524cb21b2f40c3a4518f93f91` | READY |
| Existing ALS 690_5335 | `phase-payloads/p0-audit/data/raw/als/690_5335.laz` | 110,979,201 | `01602b7385aaf7324f89da6183df3dbdeffa237f85bf57dc27208b554b4fc0b3` | READY |
| Existing ALS 690_5336 | `phase-payloads/p0-audit/data/raw/als/690_5336.laz` | 119,749,181 | `98ab7ad7f4c5108ebf41bc62186b336c6cd8a70b82fceec57136a56c0188b566` | READY |
| Existing ALS 691_5335 | `phase-payloads/p0-audit/data/raw/als/691_5335.laz` | 107,359,041 | `9e14119bb0af7d5a300aa3a2a19074219b4d6d290923b4b90277c317e8b33720` | READY |
| Existing ALS 691_5336 | `phase-payloads/p0-audit/data/raw/als/691_5336.laz` | 132,681,326 | `63c64002fc55d8b99a49749b5a2e36d802186186a950c89779463274e3cb950d` | READY |
| LoD2 reference tile | `phase-payloads/p0-audit/data/raw/lod2/690_5334.gml` | 156,656,509 | `61d29e4617bfa961e811003b7af2bb2c826b3fab90f11731f5d22b8e4689e314` | READY |
| LoD2 reference tile | `phase-payloads/p0-audit/data/raw/lod2/690_5336.gml` | 147,865,939 | `494282ee7be660401820af8efa4e2667fcaeb4d7ac8466b23be67e3347701674` | READY |
| Qualitative pilot PDF | `phase-payloads/p2-gsjso/runs/fusion_w1/20260728_fusion_w1_dense_baseline_qualitative_v5/dense_baseline_qualitative_v5.pdf` | 10,012,096 | `2c85bf526d530c55ef227097d0caf5118f250587a618674bc4753043e3657049` | READY |
| Pilot manifest | same directory, `manifest.json` | 246,040 | `1bd34ba3f6d9ae5a762746cfe0df678c537d1605dfaa170a05354fcecc3f1d3e` | READY |

`READY` above applies to exact bytes and listed identity metadata, not automatic
fitness for a condition. The two UAS LiDAR objects are `PARTIAL` because the
headers do not establish vertical datum and their raw classification is not
Roofer-ready.

## Header and coverage observations

| Asset | Header observation | Spatial/point observation | Coordinate conclusion |
|---|---|---|---|
| Pix4D MVS | LAS 1.4, point format 7, 395,312,667 points, created 2024-12-20, `Pix4Dmatic_1.58.1` | X 690739.9362–691189.0598, Y 5335816.1003–5336389.7838, Z 519.7969–603.4197 | WGS84/UTM32 + EGM96 EPSG:5773 is recorded in prior datum audit; target EPSG:25832/DHHN2016 transformation still needs a frozen recipe. |
| ULS manual | LAS 1.2, point format 3, 215,597,312 points, created 2024-12-23 | X 690787.9737–691100.7526, Y 5335834.1865–5336052.8399 | UTM32 GeoKeys/WKT are present; vertical datum is not declared. |
| ULS nadir | LAS 1.2, point format 3, 177,981,904 points, created 2024-12-23 | X 690783.6963–691260.3581, Y 5335829.5007–5336389.0657 | Same horizontal evidence; vertical datum is not declared. The low Z minimum requires explicit outlier/coverage treatment. |
| Existing ALS | LAS 1.2, point format 1, created 2022-06-16 | Four 1 km² tiles, 20,182,679–22,797,949 points/tile | Official lineage says ETRS89/UTM32 and DHHN2016; raw headers contain no CRS VLR. Derivative receipt must bind the official CRS/datum source. |
| LoD2 | CityGML tiles | Prior inspection found 12,049 stable `GroundSurface` identities and 199 candidate scene-AOI intersections | EPSG:25832/DHHN2016 evidence exists; LoD2 remains score-only except an explicitly locked exception. |

The main Docker image lacks `pyproj`, so a direct
`laspy.header.parse_crs()` audit failed with `ModuleNotFoundError`. VLR
identities, bounds, counts, and existing datum evidence were still inspected
without installing software.

## Imagery and camera identity

The current image archive contains 962 images, while the OPF/COLMAP camera
lineage exposes 937 posed images. Both archives are byte-verified, but the
25-image difference is unresolved. Until a deterministic inclusion/exclusion
ledger is frozen, image coverage, current-image identity, and the common C2–C5
base are `PARTIAL`.

## Current UAS/Drone LiDAR versus Existing ALS

The assets are distinct and must remain so.

- Current UAS/Drone LiDAR is the 2024-12-17 campaign candidate for C1
  `L_upper`. Its manual and nadir files have different bounds and gross
  densities. A fixed three-chunk, 750,000-point sample observed class 0 only.
  It therefore requires a provenance-bound class-2/6 conversion, ground
  procedure, coverage rule, and datum registration before C1.
- Existing ALS is the 2022 regional candidate for C4 `P_LiDAR`. The four
  live hashes match the tracked inventory. A fixed sample contains classes
  2, 6, 20, and 22. Its age, density, coverage, temporal change, and confidence
  must be represented as prior metadata, not as an independent truth source.
- The approximate 2.8-year separation and different platform/coverage regimes
  support separate identity; survey/derivative independence and overlap still
  require a Gate S0 receipt.

## Reference and leakage audit

| Object | Fixed search scope | Status | Consequence |
|---|---|---|---|
| Independent LoD1 prior | Git `src/configs/scripts/tests`, active phase configs/scripts, and canonical artifact filenames/GML inventory | MISSING | C5 and full `E_paired` cannot be declared ready. Do not synthesize LoD1 from the scored LoD2. |
| LoD2 reference | two exact live GML tiles plus tracked P0 evidence | READY | Score-only. RoofSurface, Z, roof type, semantic labels, and final model are prohibited from honest inputs. |
| LoD3 | same fixed search | MISSING | Not required for activation; record as unavailable reference. |
| Independent external roofprint | not searched/opened beyond checked-in declarations | UNKNOWN | Scope state is `OUT_OF_SCOPE`; do not replace with `R_ext`, and use method-specific `R_derived`. |
| Stable image/building/common-condition ledger | Git and artifact manifests | UNKNOWN | Resolver coverage and the missing LoD1 prevent an exact safe universe. |

## Candidate AOI coverage matrix

The defensible candidate scene AOI from existing P0 evidence is
EPSG:25832 X `690791.740–691154.650`, Y
`5335864.050–5336353.850`, area `177,753.3 m²`. It intersects 199
LoD2 stable identities. The count is a reference intersection count, not
`U_target`.

| Candidate AOI | Images/poses | UAS LiDAR C1 | Existing ALS C4 | MVS | LoD1 C5 | LoD2 reference | Status |
|---|---|---|---|---|---|---|---|
| Pix4D/ULS shared downtown bounds | PARTIAL: 962/937 mismatch | PARTIAL: live bytes, datum/class adapter unresolved | READY at tile coverage level; registration/independence PARTIAL | READY bytes; transformation PARTIAL | MISSING | PARTIAL: 199 candidate intersections, final stable-ID join not frozen | UNKNOWN for full C1–C5 |
| Manual-ULS tighter bounds | same | PARTIAL | READY at tile coverage level | READY bytes | MISSING | coverage join not frozen | UNKNOWN for full C1–C5 |
| Nadir-ULS wider bounds | same | PARTIAL | READY at tile coverage level | READY bytes | MISSING | coverage join not frozen | UNKNOWN for full C1–C5 |

These are candidate extents only. P1 did not select an AOI.

## `U_target → E_paired` funnel

| Funnel stage | Evidence | Status |
|---|---|---|
| Candidate buildings intersecting current scene/reference | 199 provisional LoD2 intersections | PARTIAL |
| `U_target`: current imagery + stable identity + AOI rule | No frozen AOI, 962/937 image discrepancy | UNKNOWN |
| C1 eligibility | ULS live; class/datum adapter unresolved | UNKNOWN |
| C2 eligibility | MVS live; common crop/adapter unresolved | UNKNOWN |
| C3 eligibility | GS core exists; image/camera/split unresolved | UNKNOWN |
| C4 eligibility | ALS live; prior interface/registration/independence unresolved | UNKNOWN |
| C5 eligibility | independent LoD1 not found | MISSING |
| `E_paired`: all C1–C5 attemptable | Cannot be computed safely | UNKNOWN |

No building IDs were assigned to development, validation, or held-out sets.
Missing inputs are not converted into zero eligible buildings, because the
search establishes absence only for the audited roots, not universal
nonexistence.

## Compute and storage feasibility

The qualitative pilot and protected Fusion W1 runs provide workload examples,
but they do not cover the new five-condition common pool. Without exact
`E_paired`, C1/C2 Roofer runtimes, C3–C5 training/extraction repetitions,
adapter choice, and retained artifact policy, total compute/storage is
`UNKNOWN`. Gate S0 must first run a bounded, non-held-out calibration and
publish per-building/per-condition time, peak memory, output bytes, and
failure-retention estimates. No sample-size or split decision is made here.

For scale only, the 199 candidate reference intersections imply 995
building-condition rows: 398 direct baseline rows for C1/C2 and 597 GS rows
for C3–C5. This is a schema cardinality, not an eligibility claim. The
available E5 analog used a shared AOI and six full learning runs totaling
412.2 GPU-minutes: 206.1 minutes (`3.44 GPU-hours`) for the observed first
replicate across three arms and the same for the second, `6.87 GPU-hours`
total. It used a shared AOI, so multiplying its time by 199 would be invalid
and the new total remains `UNKNOWN`. Existing bundle references are
27,601,248,424 bytes in
`artifacts/manifests/p2_run_payloads_semantic_relocation_20260730.yaml:19-36`
and 34,801,838,480 bytes in
`artifacts/manifests/fusion_w1_run_payloads_20260730.yaml:19-24`; they are not
comparable per-cell estimates. Gate S0 must freeze run granularity and
retention before using these figures.

## Gate consequence

The live store is accessible and several exact inputs are integrity-verified.
Nevertheless, related data READY claims, C1/C4 comparison, Gate S0 completion,
and P2 entry remain blocked by image identity, ULS class/datum preparation,
C4 prior independence/registration, missing LoD1, and the unresolved funnel.
