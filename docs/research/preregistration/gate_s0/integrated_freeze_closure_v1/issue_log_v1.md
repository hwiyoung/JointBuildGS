# Gate S0 integrated-freeze issue log v1

scientific_verdict: `null`

| Issue | State | Evidence | Consequence / bounded next action |
|---|---|---|---|
| `IFS0-001` persisted four-path digests | `MISSING` | One 986,484,109-byte hash pass completed, but process exited before persistence | Cannot rerun under the add-once guard; human Gate remains blocked |
| `IFS0-002` C1 parser runtime | `FIXED_NOT_RERUN` | `laspy.header.parse_crs()` required absent `pyproj`; fallback added after interruption | Requires a newly authorized replacement operation/namespace if evidence is still required |
| `IFS0-003` gravity value | `MISSING` | Computed from dense-MVS terrain normals in memory, not persisted | Cannot attest gravity vector |
| `IFS0-004` C1/C4 derivatives | `MISSING` | C1 stopped before point chunks; C4 not accessed | No per-condition coverage or residuals |
| `IFS0-005` independent UAS reference | `MISSING` | C1 processing did not complete | C2-C5 score-only reference unavailable |
| `IFS0-006` independent stable-ID spatial crosswalk | `MISSING` | LoD2 bbox use is prohibited; no independent mapping exists | `U_target`, `E_paired`, spatial groups and split are MISSING |
| `IFS0-007` C1 vertical datum | `MISSING` | Source vertical datum remains unknown | Absolute vertical scoring blocked |
| `IFS0-008` pinned Stage-3 runtimes | `PARTIAL` | Roofer exact digest and P0 tools image absent locally; common interface smoke passes | Runtime replay not READY |
| `IFS0-009` source SHA transcription | `CORRECTED_BY_ADDENDUM` | Actual DRAFT is direct approval parent | Use `f3e0be625f7b8d7ed778d74e9b9ed9ac78d58cd0`; prior records unchanged |
| `IFS0-010` successor artifact records | `PARTIAL_SCHEMA_LIMIT` | 100 is artifact_verified and locks successor artifacts object | Keep accepted attestation unchanged; cite Git task-output manifest |
