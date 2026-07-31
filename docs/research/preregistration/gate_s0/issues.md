# Gate S0 Preparation Issues

- handoff_id: `P2-W2C-GATE-S0-PREP-v1`
- proposed_status: `BLOCKED_FOR_GATE_S0_REVIEW`
- scientific_verdict: null

| ID | Status | Scope | Evidence | Required resolution |
|---|---|---|---|---|
| `S0-I01` | `MISSING` | C5 independent LoD1 | Fixed approved raw-input search contains no LoD1; only score-only LoD2 GML | Obtain an independent LoD1 with URI, bytes, SHA-256, CRS/datum, provider lineage, coverage and leakage guard |
| `S0-I02` | `MISSING` | C1 class 2/6 | Nadir/manual bounded samples contain raw class 0 only | Provenance-bound ground=2/building=6 derivative and class/coverage receipt |
| `S0-I03` | `UNKNOWN` | C1 coordinates | EPSG:32632 horizontal evidence; vertical datum and registration residual absent | Freeze EPSG:25832/DHHN2016 transformation, outlier rule and residual |
| `S0-I04` | `PARTIAL` | C2 common base | Exact 937 ledger exists, but Pix4D MVS is not hash-bound to it | Producer/replay receipt or retain sensor-processing-bundle limitation |
| `S0-I05` | `MISSING/PARTIAL` | C2 adapter | Raw MVS sample class 0; transform and building coverage incomplete | Class-2/6 derivative, transform/residual and per-building coverage |
| `S0-I06` | `PARTIAL` | C4 independence | Separate 2022 ALS and 2024 UAS files/regimes verified | Formal derivative independence, registration, overlap and confidence receipt |
| `S0-I07` | `UNKNOWN` | `U_target` | 199 reference intersections are not a stable-ID current-image universe | Outcome-free building ID/coverage ledger |
| `S0-I08` | `UNKNOWN` | `E_paired` | C1–C4 incomplete and C5 missing | All-condition eligibility and exclusion manifest |
| `S0-I09` | `PARTIAL` | `R_derived` | Contract exists; no common campaign code/config/hash | Non-GT implementation, tests, gravity binding and method-specific polygon hashes |
| `S0-I10` | `UNKNOWN` | Cost | Exact input bytes only; no comparable bounded C1–C5 calibration | Per-condition runtime, peak memory, output bytes, retry and retention ceiling on non-held-out units |
| `S0-I11` | `MISSING/PARTIAL` | Writer/toolchain | CityJSON writer/cjio partial; Roofer, val3dity, cjval, CityGML route absent in main image | Pinned callable tools, integrated writers and validators |
| `S0-I12` | `RECORDED_NONBLOCKING_ACTIVATION_ISSUE` | Offered provenance | Offered `verification.commands[2]` is descriptive prose, not executable Python | Accepted receipt explicitly rejects reliance; actual tuple and 70 repository tests rerun successfully |

No issue was hidden by replacing a missing asset, inventing a building ID,
opening held-out results, or extrapolating a protected historical run.
