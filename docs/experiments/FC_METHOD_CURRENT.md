# FC Method Current Baseline

## Purpose

This document fixes the current Footprint-Conditioned experiment policy before the next run series.

The repository should preserve source code, reproducible configs, runner/evaluation scripts, and curated decision evidence. It should not preserve raw training payloads, checkpoints, TensorBoard files, per-building readout payloads, or intermediate evidence exports.

## Current Empirical Reference

`A8_no_terrain_terms` remains the empirical reference for the next experiment series.

Reason:

- FC-S6B accepted A8 as the current terrain-off candidate.
- FC-S6D showed `A8_v2_geo` did not clearly beat A8.
- FC-S6E showed `A8_v2_joint_2pct` regressed relative to A8 and `A8_v2_geo`.
- B104 remains a guard case for hidden GroundSurface and wall-ground closure failure.

## Active Implementation Surface

The active implementation surface is Stage 2 mutual-loss control and audit instrumentation:

- split mutual terms for wall verticality, roof non-wall prior, terrain normal, and split height sides
- optional terrain confidence / mass / entropy gates
- optional terrain quantile height reference
- explicit semantic-geometry calibration channel for roof/wall only
- default-off placeholders for relation terms
- TensorBoard/audit logging for term decomposition, class statistics, and gradient diagnostics

## Allowed Next Runs

The next runs should start from the A8 legacy terrain-off reference and make only one controlled change at a time.

Allowed:

- A8 reproduction / sanity rerun
- A8 plus one default-off audit channel
- A8 plus a tightly bounded semantic-geometry calibration smoke only if the base behavior is reconfirmed

Not allowed without a new design review:

- enabling `L_structure`
- enabling G2 as the main route
- enabling roof-wall or terrain-wall relation placeholders
- increasing joint calibration strength only because the 2 percent joint run was weak
- claiming downstream success without viewer QA on guard cases

## Repository Retention Policy

Keep:

- source under `src/`
- reproducible configs under `configs/`
- reusable scripts under `scripts/`
- design specs under `docs/experiments/`
- final reports, decision files, aggregate CSV tables, and small manifests under `results/`

Do not keep:

- checkpoints
- TensorBoard event files
- raw `.npz` evidence banks
- raw `.ply` evidence files
- per-building CityJSON/readout payloads
- per-building preview screenshots
- ad-hoc launch shell scripts inside `results/`
- job record text files when a manifest exists

## Commit Boundary

Use separate commits for:

1. source/config/script changes needed to rerun the method
2. curated experiment reports and decision evidence
3. cleanup/ignore rules for raw artifacts

