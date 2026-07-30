# P0 — input-substitution audit

> Completed phase history and replay index. Repository instructions come only from
> root `AGENTS.md`; this README does not override them.

## Status

P0 compared ALS (`Ref-L`) with image-derived DIM (`Seq-G`) through the same
Roofer reconstruction and CityJSON evaluation pipeline. W1 input preparation and
diagnostics, W2 reconstruction audit, W3 metric integration, and W4 G1 reporting are
complete. The recorded observation is DIM-only reconstruction failure in 8 buildings
versus 0 for ALS (`McNemar p=0.0078`); scientific disposition remains the human
reviewer's responsibility.

Promoted evidence is in:

- `docs/evidence/p0-audit/`
- `docs/evidence/p0_g1_20260613/`
- `docs/experiments/` for later analyses that reuse P0 inputs

## Historical replay index

- `scripts/01_download.sh` through `07_vertical_align.py`: input acquisition,
  OPF/COLMAP conversion, MVS, classification, footprints, diagnostics, and datum work.
- `scripts/08_*` through `19_*`: completed W2–W4 reconstruction, diagnosis, metric,
  repeatability, closeout, and G1 packaging procedures.
- `env/`: pinned P0 Docker definitions and recorded environments.
- `runs/`: compact Git receipts; large run payloads are external artifacts.

The detailed task prompts formerly stored in nested agent files were retired because
they described completed work and could be mistaken for current commands. Git history
preserves their original wording.

## Data and artifact resolution

P0 raw/work data and large runs are stored under:

- host: `../JointBuildGS-artifacts/phase-payloads/p0-audit/{data,runs}`
- container: `/artifacts/JointBuildGS/phase-payloads/p0-audit/{data,runs}`
- resolver: `artifacts/manifests/local_workspace_20260730.yaml`

Top-level Compose exposes the canonical artifact root only at
`/artifacts/JointBuildGS`. For historical replay, `env/docker-compose.p0.yml` mounts
the sibling P0 data and runs at `/workspace/data` and `/workspace/runs` and sets
`JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS`; it does not create repo-local
`phases/p0-audit/{data,runs}`. Resolve the external artifact root before any replay.
Raw inputs are immutable; the restricted Vaihingen archive and locally sourced
TUM2TWIN bundle must not be discarded.
