# P2 C3 U_target=199 postprocess v1

- task_id: `P2-C3-UTARGET199-POSTPROCESS-v1`
- handoff_id: `P2-W2C-C3-UTARGET199-POSTPROCESS-v1`
- status: `APPROVED_FOR_EXECUTION`
- source_commit: `5030d90a85942225a6fceb6281b6e07facf42a31`
- scientific_verdict: `null`

## Exact checkpoint pair

| condition | iteration | primitives | bytes | SHA-256 |
|---|---:|---:|---:|---|
| C3-1 2DGS + semantic | 30,000 | 333,738 | 86,802,780 | `b4f8ce6d97da6d7cef216b4edb3239ac005cc44f4d45cb459a25644ed79b62ea` |
| C3-2 2DGS + semantic + image-derived MVS depth | 30,000 | 396,146 | 103,049,692 | `9bda046e2414a841e289f5d9ed0c5eaf18511445f9c52638b543cd4d52ecea12` |

Both conditions share exact seed 0, all 371,808 SfM sparse points, 103,546 neutral
dense representatives and the exact 937 common-base views.  C3-2 alone adds the frozen
image-derived MVS depth loss.  No checkpoint or seed selection is permitted.

## U_target execution

Run all 199 buildings with no visible 72/10 subgroup and no pre-execution building
exclusion.  Both condition geometries, component-derived `R_derived`, native Gaussian
center PLY and native oriented 2D Gaussian surfel-mesh PLY must be frozen before any
stable-ID bbox or independent current UAS evaluation cells are opened.

After freeze, associate each building to the component with the most frozen 1 m cell
centers inside its stable bbox, then run each selected unique component exactly once
through the common Roofer Stage-3 contract.  Roofer receives only the frozen class-2/6
evidence and component-derived `R_derived`; no external or GT roofprint is allowed.

## Required outputs

- 398 building-condition metric rows and two-condition summary CSV
- all native Gaussian centers and native oriented surfel meshes
- 8 actual gsplat panels: current RGB, GS RGB, semantic and depth for 4 views/condition
- Roofer input, output and terminal receipt for every selected unique operation
- 199 case sheets showing native point cloud, native surfel mesh, Roofer input,
  Roofer output, independent current UAS cells and reference-centered section
- qualitative HTML index, finalized/completed controls, artifact manifest, Korean
  technical report and Return

## Caps and interpretation boundary

- output namespace:
  `phase-payloads/p2/c3_utarget199_postprocess_v1/P2-C3-UTARGET199-POSTPROCESS-v1`
- project image:
  `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`
- Roofer image:
  `3dgi/roofer@sha256:dd2c415aaee337502bde0dc1426dfa9c9f88e648f9d2f6340110c49932c251d2`
- GPU render cap: 18,000 MiB; output cap: 5 GB; wall cap: 12 hours
- C1/C2 rerun: 0; G2 invocation: 0; C4/C5 access: 0
- official G3/G4/PASS_usable: `null`
- scientific_verdict: `null`

This is a non-confirmatory technical census.  Metrics and images are evidence for human
review, not a scientific approval or population/generalization verdict.  Serialized-main
role receipts are written in this operator workflow without a physical host visit.
