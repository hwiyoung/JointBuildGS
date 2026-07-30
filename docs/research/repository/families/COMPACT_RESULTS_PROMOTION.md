# Compact results promotion map

Review date: 2026-07-29

Two tracked control-plane/evidence groups were separated from payload-bearing roots without touching adjacent generated data:

| Migration | Files | Bytes | New owner |
|---|---:|---:|---|
| `DOC-IA-ARCHIVE-01` | 12 | 53,412 | `docs/evidence/archive/pre_tum_results/` |
| `DOC-IA-REPORT-01` | 9 | 840,828 | `docs/experiments/evaluation/tum2twin_surface_proxy_rv1/` and `docs/figs/tum2twin_surface_proxy_rv1/` |

All 21 source files were clean tracked files, all targets were collision-free, and payload bytes were preserved. This record describes the initial promotion wave. `STORAGE-IA-01` later externalized the remaining runtime payload, and `RESULT-IA-02` split promoted compact result files into family role directories.

Exact mappings and SHA-256 values are in [`COMPACT_RESULTS_PROMOTION_PATHS.csv`](../migrations/COMPACT_RESULTS_PROMOTION_PATHS.csv).
