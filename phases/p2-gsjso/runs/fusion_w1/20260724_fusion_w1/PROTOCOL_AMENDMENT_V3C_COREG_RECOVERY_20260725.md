# FUS-W1 protocol amendment v3c — exposure-aware coreg recovery

- Amendment ID: `FUS-W1-AMEND-V3C-COREG-RECOVERY-20260725`
- Applies after: `FUS-W1-COREG-RUN-001`
- Human authorization inherited from v3b: perform ALS-fixed camera
  co-registration while preserving LiDAR as seed and depth/normal loss source.
- Result status at amendment: lock1 is permanently `BLOCKED`; no learning,
  readout, Roofer, or scoring was started.

## 1. Why a new locked run is required

The first coreg run completed the 18-building fit stage, then opened the
trigger stage and stopped before trigger residual evaluation because
`DEBY_LOD2_4907165` did not retain both usable roof and ground samples after
the locked sampling and normal-validity filters. The run did not freeze or
publish a transform. Its runtime and compact publication remain immutable.

Removing that building and continuing the already opened trigger stage is
forbidden. This recovery is a new run namespace and a new commit. Two
premeasurement recovery preparations attempted to exclude all 36 lock1
controls: first with the surface tier and then with all three extension tiers.
Each found only 18 buildings passing the two-surface support screen. Their
original failure rows are preserved separately in
`w1_coreg2_prereg_failures.jsonl`; the formal lock2 measurement failure ledger
starts empty. No recovery correspondence or distance residual had been formed.

The final lock2 split therefore uses exposure-aware reuse. A lock1 building
whose fit residual was evaluated may appear only in lock2 `fit`, never in
`trigger` or `check`. Lock1 trigger/check alignment residuals were never
evaluated, so those buildings may enter the lock2 holdout pool after passing
the same pre-role geometry screen. The failed `4907165` is not manually
removed; it fails that screen mechanically.

## 2. Exposure-aware controls and conditional support screen

Lock2 begins from extension candidates across the pre-existing
surface, height, and outline tiers that already have both ALS and DIM
assemblies in the W2 table, positive densities, no core overlap, and at least
20 m footprint distance from the 28 core buildings. The all-tier scope is
declared after the support preparations found only 18 fully fresh candidates
meeting the two-surface availability screen; no lock2 alignment correspondence
or distance residual had been formed.

Before any alignment correspondence or distance residual is formed, every
candidate is screened with the already locked crop, ALS-derived vertical
windows, 0.4 m deterministic voxel sampling, six-neighbour/1.5 m normal
support, surface variation at most 0.15, and minimum 40 valid points. A
candidate is eligible only when ALS and photo-derived geometry each retain at
least 40 valid-normal points for both roof and ground.

The screen records counts and booleans only. It never constructs a nearest
neighbour correspondence, signed distance, or fit transform. It is nevertheless
nominal-alignment-sensitive because the two sources are tested in a shared XY
crop and photo Z support is tested against the ALS window. It is therefore a
cross-frame support inclusion screen, not independent evidence that alignment
passes. Roles are assigned only after filtering, using a new fixed tie seed and
centroid-maximin selection. Prior fit-residual-exposed controls fill only the
fit pool; trigger/check are then selected from the non-fit-exposed pool. The
result remains exactly 18 fit, 9 trigger, and 9 independent check buildings,
with a locked assertion that prior fit exposure in holdout is zero.

Accordingly, lock2 fit/trigger/check results apply only to this
support-conditioned population and cannot alone establish alignment for the
178-building queue. The final entry decision remains corrected-camera Gate A2
on the already predeclared core buildings, with no post-coreg XY retry. A Gate
A2 failure blocks learning even when lock2's conditional check passes.

## 3. Unchanged scientific and numeric contract

ALS coordinates, classes 2/6, source SHA-256, EPSG:25832, fixed
`zeta=45.700 m`, and scale 1 remain unchanged. The source COLMAP model is never
overwritten. Global identity-first selection, conditional capture blocks,
absolute criteria, adoption margins, independent check, pose equations, and
all Gate A2 thresholds remain exactly v3b.

Fit, trigger, block-fit, block-trigger, check, and pose publication remain
exact-once. Lock2 uses `results/tum_transfer/fusion_w1_coreg_lock2` and
`w1_coreg2_*` / `coreg_lock2/` artifacts. Lock1 artifacts are never reused as
parents.

## 4. Additional execution hardening before lock2

- `verify` hashes the full 937-file geometric-depth set before measurement.
- All ordinary Python exceptions are written to the runtime failure ledger and
  fail closed.
- Pose publication revalidates the full frozen-selection and independent-check
  stage-open parent chain.
- Gate A2 binds the lock2 pose manifest and check/publish stage-open receipts.
- Lock2 validates the committed lock1 publication manifest, exact artifact
  inventory, fit/select stage receipts, failure receipt, ALS hash, and absence
  of later-stage published outputs before using the exposure history.

As in v3b, a conditional block pose may be used by Gate A2, but learning then
requires a separately committed ALS-seed-aware staging path because shared
sparse points are intentionally detached. Learning remains forbidden until
coreg, Gate A2, and that seed-staging requirement all pass.
