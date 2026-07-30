# Reproducible repository scripts

Reusable, container-executed workflows are grouped by scientific role:

| Owner | Purpose |
|---|---|
| [`input_and_alignment/`](input_and_alignment/README.md) | input preparation, reconstruction, camera, CRS, and datum alignment |
| [`evidence_and_attributes/`](evidence_and_attributes/README.md) | population analysis, evidence packages, and geometry-fidelity diagnostics |
| [`e5_c001/`](e5_c001/) | reusable E5/C001 experiment orchestration |
| [`mutual_loss/`](mutual_loss/README.md) | loss diagnostics, ablation, and joint-optimization workflows |
| [`boundary_and_robustness/`](boundary_and_robustness/) | boundary, anchor, and degradation workflows |
| [`pilot_1wave/`](pilot_1wave/README.md) | approved quality-axis pilot orchestration |
| [`fair_pilot/`](fair_pilot/README.md) | cross-dataset pilot orchestration |
| [`stage3_readout/`](stage3_readout/README.md) | evidence-to-CityGML read-out workflows |
| [`evaluation/`](evaluation/README.md) | reusable evaluation workflows |
| [`inspection/`](inspection/README.md) | human-facing inspection and figure tooling |
| [`repository/`](repository/README.md) | repository inventory and maintenance checks |

An exact, lock-bound historical recipe may remain under
`phases/<phase>/scripts/<workstream>/`. Mutable run payload never belongs here.
