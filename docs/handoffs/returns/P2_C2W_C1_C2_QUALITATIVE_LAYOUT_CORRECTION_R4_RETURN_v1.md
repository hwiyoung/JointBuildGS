# Codex-to-Work Return — P2 C1/C2 qualitative layout correction R4 v1

## Return metadata

- handoff_id: `P2-W2C-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-v1`
- task_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-v1`
- source implementation commit: `92965eaff2029cc60f1a443744c418617fc204dc`
- activation commit: `936dca3dd4272af15897fe576e7e702e6013d735`
- offered commit: `6a38668840fa54da2af4d4676c406bfb67952613`
- accepted commit: `cff2d8b59acea36f4c4b48deb06f4b622eeda4a3`
- Return / 200-blocked commit: `SELF`
- 300-closed commit: `PENDING_DIRECT_CHILD_EVENT`
- run_id: `P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-RUN-v1`
- project image: `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- completed_at: `2026-08-02T19:35:43+09:00`
- proposed technical status: `BLOCKED_CONTAINER_SAFE_DIRECTORY_PREFLIGHT`
- scientific_verdict: `null`

## Answer first

R4 did not reach compact CSV inspection or rendering. The exactly authorized direct
launcher invocation ran once, fetched `origin/main`, proved the clean accepted
HEAD/config/packet tuple, passed the canonical `100-accepted` validator, and passed
its embedded Git-owned accepted-receipt and direct original-predecessor receipt
assertions. Its final exact-HEAD check then stopped with exit 1 because Git rejected
`/workspace/JointBuildGS` as dubious ownership in the read-only validation container.

The exact failing command was `git rev-parse HEAD`, called from the embedded Python
preflight. The container did not set `safe.directory=/workspace/JointBuildGS`; Git
returned status 128 and Python raised `subprocess.CalledProcessError` at `<string>`
line 30. Because the launcher uses `set -e`, it stopped before the compact CSV path
existence check, fresh R4 namespace creation, renderer, promotion, or PNG write. The
launcher was not rerun and no protected implementation was edited.

## Ownership and immutable acceptance

- The pre-pull check proved offered commit `6a38668840fa54da2af4d4676c406bfb67952613`,
  activation commit `936dca3dd4272af15897fe576e7e702e6013d735`, and source commit
  `92965eaff2029cc60f1a443744c418617fc204dc` before fast-forward.
- Closed R3 was inspected at `6dc8adf469063647a3762e7073c788f51e5fd437`;
  its writer ownership had returned to Work Host and its sole launcher had stopped
  before artifact access or output creation.
- The original predecessor `300-closed` was read from immutable commit
  `57205adf16def5382322ee57136b1cd66e9d07bc`. Its Git-blob SHA-256 is
  `7fc0770501eb3447733b481fe7ccf195064cdb3cb35934744a8db2fca6d0ec64`.
- The directly reused artifact object contains 25 records and 30,432,763 bytes with
  canonical identity
  `903b0f744c982f83106099ba280ca98d5fb362cc77867f301a31183a30bb804c`.
- Add-once accepted commit `cff2d8b59acea36f4c4b48deb06f4b622eeda4a3`
  points directly to that original predecessor and does not nest R1, R2, or R3.
- Acceptance performed zero external artifact source reads or hashes. The launcher
  preflight later read and hashed only the Git-owned predecessor receipt blob; none
  of its 25 external artifact records was opened or hashed.

## Execution counters and scope

| Counter | Observed |
|---|---:|
| direct launcher invocations | 1 |
| launcher-body entries | 1 |
| origin fetches inside launcher | 1 |
| clean packet/config/HEAD authority passes | 1 |
| activated packet parser passes | 1 |
| canonical accepted-receipt validator passes inside launcher | 1 |
| embedded Git-owned accepted receipt reads | 1 |
| embedded Git-owned original-predecessor receipt reads / hashes | 1 / 1 |
| embedded exact-HEAD `git rev-parse` attempts / failures | 1 / 1 |
| compact reference-cell CSV path inspections | 0 |
| compact reference-cell CSV natural reads / digests | 0 / 0 |
| predecessor external artifact reads / hashes | 0 / 0 |
| fresh R4 namespace creations | 0 |
| renderer process executions | 0 |
| promotion executions | 0 |
| new PNG writes / post-write digests | 0 / 0 |
| scientific calculations / eligibility recomputations | 0 / 0 |
| validation / held-out accesses | 0 / 0 |
| Roofer / reconstruction / MVS / LiDAR / GS / C3-C5 executions | 0 |

The host launcher checked only that the artifact root itself was an existing absolute
non-symlink directory. It did not inspect the compact CSV path. The failed container
had only a read-only repository mount and no external artifact-root mount.

## Output and visual status

Planned external URI:

`artifact://JointBuildGS/phase-payloads/p2-baselines/c1_c2_qualitative_layout_correction_r4_v1/P2-C1-C2-QUALITATIVE-LAYOUT-CORRECTION-R4-v1/`

Observed execution state: `NOT_CREATED_BY_R4`. No report, technical manifest, or PNG
was promoted. Consequently 2520x1400 decoding, original-pixel P1/P2/P3/F1/F2/F3/F4
inspection, and F1-F4 rejection-reason containment review are `NOT_PERFORMED`; no
visual PASS is claimed.

## Preserved predecessor results

This pre-artifact technical failure did not alter any C1/C2 number or criterion state:

- C1 G0/G1 remains `51/51` and `51/51`;
- C2 G0/G1 remains `50/51` and `50/51`;
- C2 full/partial/absent remains `46/4/1`;
- G2/G3/G4/`PASS_usable` remains `PENDING`;
- `scientific_verdict` remains `null`.

## Verification and closure

The canonical validator passed the committed `100-accepted` receipt before execution
and again inside the sole launcher invocation. Focused renderer/promotion tests were
not run because the packet schedules them only after launcher success, which did not
occur.

This Return and add-once `200-blocked` receipt preserve the direct original-predecessor
attestation without external artifact access. A separate direct-child `300-closed`
returns exclusive writer ownership to Work Host. R1, R2, and R3 receipt chains and
namespaces remain closed and untouched. Any correction requires a new reviewed handoff
identity; this R4 body must not be rerun or reopened.

`scientific_verdict` remains `null`.
