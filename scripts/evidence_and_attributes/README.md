# Evidence and attribute workflows

Reusable evidence construction and attribute analysis are grouped by purpose:

| Directory | Role |
|---|---|
| `population_analysis/` | population descriptors, texture anchors, and outcome associations |
| `review_packages/` | evidence cards and human-review packages |
| `geometry_fidelity/` | surface, facet, density, and over-segmentation fidelity checks |
| `diagnostic_tables/` | reproducible D4/D5/D12 tables, figures, and batch drivers |

These scripts may consume compact phase receipts, but reusable implementations
and cross-workstream imports resolve through the semantic `scripts/` and `src/`
owners rather than `phases/<phase>/scripts`.
