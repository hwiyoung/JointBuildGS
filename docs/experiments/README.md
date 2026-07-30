# Experiment evidence

This tree contains compact, reviewable experiment evidence. It is organized by
**scientific purpose first** and **experiment family second**. A family keeps its
existing identifier so reports, tables, metrics, and manifests remain traceable.

## Purpose groups

| Group | Owns | Families |
|---|---|---:|
| [`input-and-alignment/`](input-and-alignment/README.md) | inputs, CRS/datum alignment, projection, and evidence preparation | 17 |
| [`joint-optimization/`](joint-optimization/README.md) | Stage 2 losses, training arms, ablations, and optimization mechanisms | 27 |
| [`citygml-readout/`](citygml-readout/README.md) | Stage 3 evidence-to-CityGML read-out | 7 |
| [`evaluation/`](evaluation/README.md) | scoring, validation, diagnostics, fidelity, and regression | 22 |
| [`pilots/`](pilots/README.md) | bounded pilot studies and active experimental waves | 7 |
| [`research-operations/`](research-operations/README.md) | audits, briefings, evidence assembly, and consolidation | 4 |

## Family layout

- `reports/` — human-readable reports, decisions, QA indexes, and notes
- `tables/` — compact CSV evidence tables
- `metrics/` — machine-readable summary metrics
- `manifests/` — experiment provenance and compact model metadata
- `models/` — exceptional small curated geometry/model evidence only

Runtime status and self-verification receipts belong under `phases/`. Full
checkpoints, renders, images, point clouds, generated meshes, and caches live in
external artifact storage; `artifacts/manifests/` records how to resolve them.

