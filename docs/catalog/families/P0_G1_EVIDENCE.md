# P0 G1 evidence migration

Review date: 2026-07-29  
Migration: `DOC-IA-08`

The 112-file, 19,685,795-byte P0 G1 review package moved from the phase documentation tree to `docs/evidence/p0_g1_20260613/`. All original payload SHA-256 values are preserved in [`P0_G1_EVIDENCE_PATHS.csv`](../migrations/P0_G1_EVIDENCE_PATHS.csv).

P0 remains a closed self-contained execution bundle. Its container continues to expose the package at `/workspace/docs/G1_package` through an explicit nested bind mount. Historical run contents and the package's internal relative manifest paths were not rewritten.

This separates responsibilities without breaking reproduction:

- `docs/evidence/p0_g1_20260613/` owns the reader/reviewer package;
- `phases/p0-audit/` owns the phase rules, scripts, environment, data contracts, and run receipts;
- the Compose compatibility mount connects the closed scripts to the promoted package.
