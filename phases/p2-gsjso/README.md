# P2 — GS-JSO core

> Active phase status and ownership index. Repository instructions come only from
> root `AGENTS.md`; this README does not override them.

## Current status

P2 is active. The current workstream is **Fusion W1**, which integrates geometric and
semantic evidence on gsplat-based planar primitives and carries that evidence into the
Stage 3 read-out. No scientific verdict is assigned by this index.

Current owners:

- reusable implementation: `src/`
- reusable configs and drivers: `configs/`, `scripts/`
- automated verification: `tests/fusion_w1/`
- phase-locked Fusion controls and compact receipts:
  `phases/p2-gsjso/{configs,scripts,runs}/fusion_w1/`
- promoted reports: `docs/experiments/pilots/fusion_w1/`
- issue record: `phases/p2-gsjso/docs/issues.md`
- external payload resolver: `artifacts/manifests/fusion_w1_run_payloads_20260730.yaml`

Treat the active Fusion W1 control plane and user changes as protected. Large payloads
resolve through `JBGS_ARTIFACT_ROOT=/artifacts/JointBuildGS`; they are not owned by Git.

## Research context

P2 addresses the P0 observation that image-derived point-cloud intermediates can fail
in texture-poor or noisy regions. The durable definitions of `L_mutual`,
`L_structure`, semantics, gravity, ablations, and Stage 3 are maintained in
`docs/research/RESEARCH_CONTEXT.md` and `docs/research/EXPERIMENT_PLAN.md`.

The former nested P2 agent file contained an explicitly unapproved “5-way DRAFT” and
provisional success thresholds. It was retired so those guesses cannot be applied as
current instructions. Git history preserves it as historical context; only an approved
lock or current workstream config may define an experiment gate.

## Phase lifecycle

`phases/` keeps only phase-local locked configs/procedures and compact receipts.
Reusable code is promoted into `src/`, `scripts/`, or `configs/`; promoted reports and
tables belong in `docs/experiments/`; large checkpoints, renders, and run payloads are
external and referenced by manifests.
