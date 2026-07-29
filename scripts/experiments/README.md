# Experiment drivers

| Family | Driver location | Evidence location |
|---|---|---|
| Boundary map | [`boundary_map/`](boundary_map/README.md) | `docs/experiments/boundary_map/` |
| Degradation curve | [`degradation_curve/`](degradation_curve/README.md) | `docs/experiments/degradation_curve/` |
| E5 C001 S3B0 | [`e5_c001_s3b0/`](e5_c001_s3b0/README.md) | `docs/experiments/e5_c001_s3b0/` |
| Pilot one-wave | [`pilot_1wave/`](pilot_1wave/README.md) | `phases/p2-gsjso/runs/20260721_pilot_1wave/` and related reviewed documents |

These directories own reusable orchestration code, not run payloads. Immutable receipts stay in `phases/`, compact reviewed evidence stays in `docs/`, and large generated outputs remain in ignored or external artifact storage.
