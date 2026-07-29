# P2 reusable-code migration wave 1

## Decision

Promote only the P2 implementation families that are reusable outside one immutable receipt and whose references can be updated without rewriting historical manifests:

| Family | Drivers | Tests | New owner |
|---|---:|---:|---|
| Degradation curve | 4 | 0 | `scripts/experiments/degradation_curve/` |
| E5 C001 S3B0 | 14 | 5 | `scripts/experiments/e5_c001_s3b0/`, `tests/experiments/e5_c001_s3b0/` |
| Pilot one-wave | 17 | 24 | `scripts/experiments/pilot_1wave/`, `tests/experiments/pilot_1wave/` |
| **Total** | **35** | **29** | **64 tracked paths** |

The exact old/new paths and before/after hashes are recorded in `docs/catalog/migrations/P2_SCRIPT_PATHS_WAVE1.csv`.

## Preserved phase-local boundary

Primary4, S3A′, shared historical metric/read-out helpers, frozen configs, run receipts, recovery evidence, and any script whose path or SHA is asserted by a committed lock remain in `phases/p2-gsjso/`. This is a deliberate reproducibility boundary, not unfinished filing.

The degradation recovery helper remains byte-identical. Its QA accepts the old path key embedded in the frozen manifest and validates that hash against the moved file; the historical manifest itself is unchanged.

## Storage and execution boundary

Only source and tests move. Datasets, checkpoints, point clouds, meshes, images, logs, caches, and run outputs do not move. Drivers continue to run through Docker and continue to address phase-local receipts and locked dependencies by explicit repository-relative paths.
