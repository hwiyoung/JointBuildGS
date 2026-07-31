# Gate S0 Remediation R1 Issue Log v1

- handoff_id: `P2-W2C-GATE-S0-REMEDIATION-R1-v1`
- proposed_status: `BLOCKED_FOR_GATE_S0_REMEDIATION_REVIEW`
- scientific_verdict: null

| ID | Priority | Status after R1 | Evidence / change | Required resolution |
|---|---|---|---|---|
| `S0-I01` | P0 | `MISSING` | No independent LoD1 bytes in fixed scope. Official LDBV LoD1 derives from updated LoD2 and is inadmissible for honest C5 | Acquire/license/hash-bind a truly independent LoD1 with CRS/datum, date, coverage and leakage guard |
| `S0-I02` | P0 | `MISSING` | C1 exact raw source remains class 0; no immutable class-2/6 derivative | Approved non-GT ground/building classifier, derivative bytes/hash and per-ID coverage |
| `S0-I03` | P0 | `UNKNOWN` | C1 horizontal EPSG:32632 is bound; vertical datum and registration residual remain absent | Freeze 25832/DHHN2016 pipeline, outlier rule and residual checks |
| `S0-I04` | P0 | `RESOLVED_AS_MISMATCH` | Published MVS used 1,104 acquired images; public set is 962 and OPF calibrated set is 937 | Retain `sensor-processing-bundle baseline`; prohibit method-only C2-vs-C3 interpretation |
| `S0-I05` | P0 | `MISSING/PARTIAL` | C2 EGM96 metadata is bound, but class derivative, target transform and building coverage are incomplete | Class-2/6 derivative, validated vertical transform/residual and coverage |
| `S0-I06` | P0 | `PARTIAL` | C4 ALS is a separate provider/sensor/byte regime from C1 UAS LiDAR | Bind exact ALS acquisition/version, registration, per-ID overlap, confidence semantics and interface |
| `S0-I07` | P0 | `UNKNOWN` | 199 stable reference IDs and provider IDs are reproducible, but no current-image building coverage join exists | Outcome-free image/frustum or equivalent building-level support ledger |
| `S0-I08` | P0 | `UNKNOWN` | C1–C4 eligibility joins incomplete and C5 missing | Complete all-condition attemptability/exclusion manifest before `E_paired` |
| `S0-I09` | P0 | `PARTIAL` | Contract exists; no canonical non-GT `R_derived` implementation/hash or terrain-MVS gravity | Common derivation code/config/tests, gravity vector/hash and method polygon hashes |
| `S0-I10` | P1 | `UNKNOWN` | No performance/cost run was authorized; exact input bytes alone are not a cost ceiling | Separately approved non-held-out calibration after data/toolchain readiness |
| `S0-I11` | P0 | `MISSING/PARTIAL` | cjio/CityJSON partial; current image lacks Roofer, CityGML route, cjval, val3dity and G0–G4 writers | Make pinned common toolchain locally callable and integration-tested |
| `S0-I12` | P3 | `CLOSED_NONBLOCKING` | Prior offered-command prose issue was transparently handled by executable verification | No further scientific action |
| `S0-R13` | P0 | `SOURCE_READY_INTEGRATION_PARTIAL` | OPF contains 4,131,648-point sparse reconstruction; 937 sparse camera UIDs exactly equal calibrated IDs; all members hash-bound | Pin/replay OPF→COLMAP and undistortion, then bind derivative outputs; never substitute dense MVS |
| `S0-R14` | P0 | `PARTIAL` | Geometry candidate, structure reference IDs/CRS and overlap classes recorded; C1 is self-reference if current UAS LiDAR scores C1 | Freeze geometry/structure reference versions, uncertainty and per-building production/source overlap |
| `S0-R15` | P1 | `PARTIAL` | Local manual UAS is Zenodo v1.0 bytes and differs from current v1.2, while nadir proposal is version-stable | Keep exact version matrix and do not label manual candidate latest |
| `S0-R16` | P0 | `BLOCKING` | 199-row funnel has exact stable IDs, but C1/C2/C4 bbox values are unregistered diagnostics and C3 has no building visibility member | Registered per-ID condition coverage and current-image join |

## Guard status

- No scored LoD2 Z, `RoofSurface`, roof type, semantics or final model entered an honest arm.
- No LoD2-derived LoD1 was created.
- No dense MVS initialized or supervised C3–C5.
- No performance baseline, GS training, prior-loss tuning, production derivative or cost run occurred.
- Held-out, Fusion W1 and `R_ext` were not accessed.
- No adapter, G3/G4 threshold, Gate decision or scientific verdict was produced.
