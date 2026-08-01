# Codex-to-Work Return — Gate S0 Common-Base Lineage R2B v1

## Return metadata

- handoff_id: `P2-W2C-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1`
- task_id: `P2-GATE-S0-COMMON-BASE-LINEAGE-R2B-v1`
- accepted commit: `1a4fb69d03dc156e54bb789baa1c4fa56ef2ea58`
- output commit: `SELF`
- verified receipt commit: `PENDING_SEPARATE_200_EVENT`
- closed receipt commit: `PENDING_SEPARATE_300_EVENT`
- proposed status: `BLOCKED_FOR_GATE_S0_TECHNICAL_AND_HUMAN_FREEZE`
- P2 performance: PROHIBITED
- scientific_verdict: null

## Scope completion

R2B completed the manifest-first investigation of the retained P0 exact-937 chain,
bounded live metadata confirmation, a new no-repeat resolver namespace, exact member
crosswalk, separated component readiness, LF/CRLF-portable protected-scope checks,
regression tests and this Return. It generated no dense MVS, depth, normal,
confidence, segmentation, gravity, LoD1 or performance output.

## Exact lineage determination

All exact-member observations reproduce included-basename set SHA-256
`dd9b446e11c978ef8223858f08571bfea832e0d33517b24c1e573060244f4e2c`:

- 937 retained `colmap_dense/images` members;
- 937 Git source-ledger included rows and unique source camera UIDs;
- 937 COLMAP sparse image IDs using one COLMAP camera-model ID;
- 937 `patch-match.cfg` and 937 `fusion.cfg` members;
- 937 successful OpenMVS log image names;
- 937 geometric + 937 photometric depth maps;
- 937 geometric + 937 photometric normal maps.

The retained chain has exact path/count/byte agreement with the Git retention plan:

| Path | Files | Bytes |
|---|---:|---:|
| `colmap_dense/images` | 937 | 910,980,034 |
| `colmap_dense/sparse` | 5 | 147,971,170 |
| `colmap_dense/stereo` | 3,750 | 22,751,489,085 |
| `openmvs/scene.mvs` | 1 | 23,267,921 |
| `openmvs/dim_dense.ply` | 1 | 659,138,498 |
| `dim/dim_v1.laz` | 1 | 156,106,520 |

The exact producer script is blob `bf5cd4dac48b3ee622e0e82a1e00063eaa00c097`
in commit `252ea1dce31acec53481876137941192fea9a9bc`. The run-recorded
`6d924793c367f93a3abe0447fbd9057f407fe036` is the parent/logger snapshot and does
not contain the executable. The successful route binds exact-937 COLMAP input to
`scene.mvs`, then 43,942,554-point `dim_dense.ply`, then translated EPSG:25832
`dim_v1.laz`. Existing large-payload digests and the vertical datum remain unbound.

Depth and normal existence/member lineage is exact, but producer execution lineage
is only PARTIAL: their 2026-06-24 creation is not backed by a durable exact invocation
log. Filename/member equality is not treated as a sufficient producer attestation.

## Component readiness

| Component | Gate readiness | Key reason |
|---|---|---|
| source membership | READY | exact 962 / 937 / 25 selected by DEC-P1-012 |
| SfM sparse | PARTIAL | exact member/producer route; retained digest and human role decision pending |
| dense MVS | PARTIAL | exact-937 chain; retained digest, vertical datum and candidate acceptance pending |
| depth | PARTIAL | exact-937 x2 existence; producer invocation and ON/OFF pending |
| normal | PARTIAL | exact-937 x2 existence; producer invocation and ON/OFF pending |
| confidence | MISSING | no exact candidate; ON/OFF pending |
| segmentation | MISSING | no exact candidate; ON/OFF pending |
| gravity | MISSING | required once from selected terrain MVS normals; not authorized here |

New sparse or dense preprocessing is unnecessary if the human Gate accepts this
retained chain. A new depth/normal run is not yet decidable and must not be scheduled
before producer-lineage recovery and component enablement. Confidence/segmentation
generation is conditional on human enablement. Gravity generation is required later
by the root invariant, after its input source is bound.

## No-repeat and byte accounting

- first resolver invocation: protected external payload read/hash `0 / 0` bytes;
- bounded metadata first invocation: read/hash `564,247 / 564,247` bytes;
- retained filesystem metadata: 4,698 statted entries;
- exact second invocation: external payload `0 / 0`, external metadata `0 / 0`,
  output read/hash `0 / 0`, writes `0`;
- completed ledger before/after SHA-256:
  `efd55cff2cae48e0cd304ee1ce8ce9838b8d2bc70b7f462fe340fd42ffb1ec91`;
- R1 15.7 GB bundle, Images.zip, OPF.zip, retained payloads/trees and R2A outputs:
  no full reread and no full rehash;
- generated scientific derivatives: none.

The one proposed future digest task is conditional on retained-chain acceptance and
has an exact maximum of `986,484,109` bytes over only `colmap_dense/sparse`,
`scene.mvs`, `dim_dense.ply` and `dim_v1.laz`.

## Remaining technical items

1. If the retained chain is accepted, bind its four-path compact sparse/dense payload
   identity with the separately authorized one-pass ceiling above.
2. Recover the exact 2026-06-24 depth/normal producer invocation or classify those
   maps ineligible.
3. Bind vertical datum and the canonical transform contract.
4. After human enablement, create only the still-required confidence/segmentation
   evidence and the mandatory one-time gravity estimate.
5. Bind an exact C5 primary evaluation reference independent of the input LoD2.
6. Close the remaining AOI, `U_target`, `E_paired`, eligibility, split, toolchain and
   cost items in the Gate S0 freeze packet.

## Remaining human decisions

1. Accept or reject the retained exact-937 sparse/dense chain and its bounded digest
   follow-up.
2. Freeze depth, normal, confidence and segmentation ON/OFF states.
3. Approve an exact independent C5 evaluation-reference binding before primary C5.
4. Make the separate final Gate S0 decision after all technical evidence is closed.

The next single bounded action is decision 1. This Return does not make that decision,
does not approve primary C5 or Gate S0, and does not authorize P2 performance.

## Writer return contract

After the R2B output commit is pushed and the Docker suite passes against exact
`origin/main`, the Experiment Host will add immutable `200-verified` and direct-child
`300-closed` event commits. The closed event returns exclusive writer ownership to
the Work Host. Receipt commits, exact commands and final SHAs are intentionally
recorded in the add-once receipt files rather than guessed in this pre-receipt Return.
