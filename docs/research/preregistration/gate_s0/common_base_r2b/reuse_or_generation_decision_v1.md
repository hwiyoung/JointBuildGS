# Gate S0 R2B — Existing Common-Base Reuse or Generation Decision

- task_id: `P2-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1`
- source candidate: `B_CURRENT_CANDIDATE_c205892c390997b5`
- research canon: `C1C5_CANON_v2` through `DEC-P1-012`
- proposed technical status: `BLOCKED_FOR_GATE_S0_TECHNICAL_AND_HUMAN_FREEZE`
- P2 performance: PROHIBITED
- scientific_verdict: null

## Outcome

The retained P0 chain is an exact-937 common-source derivative candidate. The
relation is not inferred from filename substrings. The exact case-sensitive source
set hash `dd9b446e...44f4e2c` is reproduced by all of the following independently:

- the frozen Git source ledger;
- retained `colmap_dense/images` directory membership;
- the T3 image list and COLMAP sparse image mapping;
- `patch-match.cfg` and `fusion.cfg`;
- the successful OpenMVS densification log;
- all four retained geometric/photometric depth/normal member sets.

The exact P0 producer executable is Git blob
`bf5cd4dac48b3ee622e0e82a1e00063eaa00c097`, first contained by commit
`252ea1dce31acec53481876137941192fea9a9bc`. The run's recorded commit
`6d924793c367f93a3abe0447fbd9057f407fe036` is that commit's parent and did not yet
contain `03_mvs.sh`; it is retained as the logger snapshot, not misreported as the
executable-containing commit.

The successful chain is:

`exact-937 OPF/COLMAP sparse` → `colmap_dense/images + sparse` →
`InterfaceCOLMAP / scene.mvs` → `DensifyPointCloud / dim_dense.ply` →
`PDAL translation / dim_v1.laz (EPSG:25832)`.

## Component disposition

| Component | Exists | Exact lineage | Gate readiness | Enablement | Generation disposition |
|---|---|---|---|---|---|
| source membership | yes | exact 962/937/25, frozen by DEC-P1-012 | READY | fixed | unnecessary |
| SfM sparse | yes | exact-937 member and producer route | PARTIAL | human Gate decision | duplicate generation unnecessary if retained chain is accepted |
| dense MVS | yes | exact-937 producer chain; payload digest pending | PARTIAL | required for C2; candidate acceptance pending | new dense run unnecessary if retained chain is accepted |
| depth | 937 geometric + 937 photometric | exact membership; producer invocation unbound | PARTIAL | human ON/OFF | not yet decidable |
| normal | 937 geometric + 937 photometric | exact membership; producer invocation unbound | PARTIAL | human ON/OFF | not yet decidable |
| confidence | no | none | MISSING | human ON/OFF | conditional |
| segmentation | no | none | MISSING | human ON/OFF | conditional |
| gravity | no | none | MISSING | required by root invariant | generate later once from selected terrain MVS normals; never hardcode |

The depth and normal files have 2026-06-24 timestamps, while the retained exact
COLMAP configs and P0/OpenMVS run receipts do not bind that invocation. Exact member
equality therefore proves membership, not a fully closed producer execution identity.

## Reuse and byte budget

R2B reused the Git retention plan/receipt, the R1 sparse member attestation, R2A
compact metadata, and bounded P0 configs/logs. It generated no scientific derivative.
The resolver's first inventory read and hashed `564,247` bytes of declared bounded
metadata and statted `4,698` directory/file entries. It read and hashed zero bytes of
the protected large payloads.

The immediate exact second invocation used an intentionally nonexistent artifact
root. It returned `REUSED_COMPLETED` before artifact-root resolution with external
payload read/hash `0/0`, external metadata read/hash `0/0`, output read/hash `0/0`,
and writes `0`. The completed ledger SHA-256 remained
`efd55cff2cae48e0cd304ee1ce8ce9838b8d2bc70b7f462fe340fd42ffb1ec91`.

If the retained sparse/dense chain is selected for the Gate freeze, one separate,
approved single pass may bind only:

- `colmap_dense/sparse` — 147,971,170 bytes;
- `openmvs/scene.mvs` — 23,267,921 bytes;
- `openmvs/dim_dense.ply` — 659,138,498 bytes;
- `dim/dim_v1.laz` — 156,106,520 bytes.

The exact ceiling is `986,484,109` bytes. This R2B task did not perform that pass and
does not authorize it. Images.zip, OPF.zip, the R1 bundle, retained images/stereo
trees, and R2A outputs remain outside the hash scope.

## C5 constraint

The R2A LoD2-derived LoD1 remains the selected C5 input candidate, with its existing
immutable labels `REFERENCE_DERIVED_DIAGNOSTIC_ONLY` and
`REFERENCE_DERIVED_SELF_CONDITIONED`, and `primary_c5_eligible=false`. An exact
evaluation reference independent of the input LoD2 remains unbound. R2B neither
promotes primary C5 nor changes the R2A labels.

## Next bounded Gate decision

The next single bounded action is a human Gate decision to accept or reject the
retained exact-937 sparse/dense chain as the common-base candidate and, only if
accepted, authorize the specified `986,484,109`-byte maximum one-pass digest task.
That decision does not approve Gate S0 or P2 performance.
