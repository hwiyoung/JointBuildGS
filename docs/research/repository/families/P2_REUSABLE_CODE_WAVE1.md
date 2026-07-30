# P2 reusable-code migration wave 1

## Decision

Promote only the P2 implementation families that are reusable outside one immutable receipt and whose references can be updated without rewriting historical manifests:

| Family | Drivers | Tests | New owner |
|---|---:|---:|---|
| Degradation curve | 4 | 0 | `scripts/boundary_and_robustness/degradation_curve/` |
| E5 C001 S3B0 | 14 | 5 | `scripts/e5_c001/s3b0/`, `tests/e5_c001/s3b0/` |
| Pilot one-wave | 17 | 24 | `scripts/pilot_1wave/`, `tests/pilot_1wave/` |
| **Total** | **35** | **29** | **64 tracked paths** |

The exact old/new paths and before/after hashes are recorded in `docs/research/repository/migrations/P2_SCRIPT_PATHS_WAVE1.csv`.

## Preserved phase-local boundary

Primary4, S3A′, shared historical metric/read-out helpers, frozen configs, run receipts, recovery evidence, and any script whose path or SHA is asserted by a committed lock remain in `phases/p2-gsjso/`. This is a deliberate reproducibility boundary, not unfinished filing.

The degradation recovery helper remains byte-identical. Its QA accepts the old path key embedded in the frozen manifest and validates that hash against the moved file; the historical manifest itself is unchanged.

## Post-move validation hardening

`P2-CODE-IA-02` closed four path-boundary gaps found by an independent read-only audit:

- the frozen phase-local read-out extractor remains byte-identical, while its container receives an explicit pilot-family `PYTHONPATH`;
- scoring imports its phase-local locked metric helpers from an explicit shared-script search path;
- the pilot clean-tree gate now covers the promoted pilot driver directory;
- degradation preflight uses the canonical boundary-map and QS baseline document paths.

Historical manifests, receipts, locked metric hashes, and missing artifact payloads were not rewritten or synthesized.

## Storage and execution boundary

Only source and tests move. Datasets, checkpoints, point clouds, meshes, images, logs, caches, and run outputs do not move. Drivers continue to run through Docker and continue to address phase-local receipts and locked dependencies by explicit repository-relative paths.
