# Gate S0 freeze packet v2 — human-review draft

Task: `P2-GATE-S0-INTEGRATED-FREEZE-CLOSURE-v1`
Technical state: `BLOCKED`
gate_decision: `null`
scientific_verdict: `null`

This is a technical evidence draft for human review. It does not approve Gate S0,
P2 entry, condition execution, performance access, or a scientific conclusion.

## Integrated status

| Component | State | Frozen result / blocker |
|---|---|---|
| immutable source ancestry | `READY` | actual DRAFT `f3e0be625f7b8d7ed778d74e9b9ed9ac78d58cd0` → approval `58a3c2578cbb9aa91f982934bd75aa1ce1737bc2` → offered `4d47fe3bf3f23aa631b9f9073ace4f2bf7572615`; clerical SHA corrected only by addendum |
| common source membership | `READY` | `B_CURRENT_CANDIDATE_c205892c390997b5`, exact 962 / 937 / 25 |
| component defaults | `READY` | sparse/dense/gravity ON; depth, normal-map supervision, confidence and segmentation OFF |
| retained-chain persisted identity | `MISSING` | one allowed 986,484,109-byte pass completed, but all digest/member values were lost on process exit; rerun prohibited |
| retained producer lineage | `PARTIAL` | `STRONGLY_CORROBORATED_PRODUCER_ROUTE / PARTIAL`, not exact run-script attestation |
| EPSG:32632→25832 contract | `READY` | explicit WGS84 UTM32 inverse → GRS80 UTM32 forward; three PROJ 9.3.1 checks, max residual 0.000231 m |
| vertical datum | `MISSING` | C1 unknown; no silent DHHN2016 equivalence |
| gravity value | `MISSING` | computed once from selected dense-MVS terrain normals in memory but not persisted |
| C1 current nadir UAS derivative | `MISSING` | absent `pyproj` caused header-CRS parse failure before first point chunk |
| C4 four-tile 2022 ALS derivative | `MISSING` | not accessed after C1 failure |
| independent current-UAS-LiDAR reference | `MISSING` | not constructed; no stable-ID join performed |
| C5 provenance independence | `READY` | LoD2-derived coarse LoD1 is input only; never reference/crop/tuning/primary evidence; LoD2 geometry assets not opened |
| exact 199-row eligibility ledger | `MISSING` | prior count/set digest retained, but no admissible independent per-ID spatial crosswalk/reference freeze |
| exact `U_target` / `E_paired` | `MISSING` | counts and hashes remain null; no false empty set substituted |
| exhaustive spatial split | `MISSING` | seed/algorithm frozen, but no `E_paired` or independent spatial groups; held_out_accessed=false |
| common non-GT Stage-3 interface | `PARTIAL` | one interface for C1-C5 rejects external roofprints; in-memory synthetic smoke passes; pinned Roofer/P0 images absent and gravity missing |
| administrative cost caps | `READY` | 1 RTX-3090-class GPU, 24 GB VRAM, 12 h/run, 100 GB/run, one retry, 500 GB total |
| prohibited access guard | `READY` | no stereo, Images.zip, OPF.zip, R1 15.7 GB, LoD2 geometry asset, held-out, Fusion W1, R_ext, or performance access |

## Exact one-pass execution record

Resolved Experiment Host root:
`/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts`
(`artifact://JointBuildGS`, container `/artifacts/JointBuildGS`), host `innopam-AI`.

Accepted execution image:
`sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`.

Command:

```text
docker exec -u 1000:1000 jointbuildgs-dev bash -lc 'cd /workspace/JointBuildGS && python scripts/input_and_alignment/gate_s0/integrated_freeze_closure_v1/run_integrated_freeze.py --artifact-root /artifacts/JointBuildGS'
```

Operation ID:
`58f1f62d461d5a45c0d740094ff5042701c6cae27a0278e3235ccc60a9f709d9`.
Executed runner blob: `97ebc6d891d1a6151d266460925bce128a716742`.
Config blob: `9b12b633f2bbe4b6baa8264573dcd719cce94a4b`.

The stage trace proves completion of sparse, scene, dense PLY and dense LAZ functions
and their exact byte assertions before entering C1. This accounts for exactly four
logical paths, eight regular files and 986,484,109 bytes read and hashed once. The
digest values were not printed or persisted before the subsequent exception and are
therefore `MISSING`, not reconstructed.

`laspy` 2.6.1 called `header.parse_crs()`, which imported absent `pyproj`. The run
failed before C1 point-chunk decoding. C1 actual header I/O bytes are unknown because
the LAZ backend was not instrumented. C4 was not accessed.

The add-once started record is 530 bytes and the partial MVS derivative is 5,464,707
bytes by exact-path stat. Recovery performed six exact-path metadata probes, zero
directory enumeration and zero content read/hash. Their hashes remain null. The
started marker ensures any invocation without a completed ledger blocks before
external access.

## Reference and leakage contract

C1 remains `SELF_REFERENCE_UPPER_BASELINE`. The intended C2-C5 reference is a
score-only current-UAS-LiDAR reference. It was not produced. Input LoD2 geometry was
not opened or used for geometry, registration, cropping, tuning, stopping, gravity,
or primary evidence. The C5 LoD1 remains explicitly LoD2-derived input provenance.

The static implementation froze reference geometry before any identity access and
restricted the historical candidate ledger to first-field stable IDs; bboxes were not
parsed or used. Since execution stopped before reference freeze, even the identity join
was not run. No 199-row eligibility status, target universe, paired universe, spatial
group, or held-out assignment is claimed.

## Stage-3 and cost contract

`R_DERIVED_NON_GT_CONVEX_HULL_V1` consumes only class-6 points, derives its own
roofprint and rejects an external roofprint. Docker unit tests cover all five condition
labels and external-roofprint rejection. The in-memory CityJSONSeq smoke contains six
records/five features, 3,443 bytes, SHA-256
`ca3697c657730581338006ed50570d91d3a7639f7ac7f60e3c0b410893d04935`, and no quality
comparison. No building quality or performance run occurred.

The exact Roofer 1.0.0 digest and `jointbuildgs-p0-tools:t0` were not locally
available. No unpinned substitute was used.

Administrative caps for any separately authorized later run are: one RTX-3090-class
GPU, at most 24 GB VRAM, at most 12 hours, at most 100 GB new output, at most one
retry, and at most 500 GB total new retained storage.

## Human Gate question

Technical Gate S0 closure and P2 entry are **not supportable** from this packet.
The one next bounded action is a human decision whether to authorize a replacement
integrated-freeze operation in a new immutable task/namespace, with the corrected
CRS-parser fallback and an admissible independent stable-ID spatial crosswalk/vertical
datum supplied in advance. The failed namespace must remain untouched.

gate_decision: `null`
scientific_verdict: `null`
