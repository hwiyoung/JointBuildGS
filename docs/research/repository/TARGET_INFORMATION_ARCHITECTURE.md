# Target information architecture

## One rule

Every file has one owner selected by role. Research area and experiment purpose form the path; file extension does not.

```text
JointBuildGS/
├── src/                 reusable implementation and browser apps
├── configs/             reusable declarative parameters
├── scripts/             reproducible workflows grouped by purpose
├── tests/               automated contracts and small fixtures
├── docs/
│   ├── research/        method, preregistration, decisions, repository map
│   ├── experiments/     <purpose>/<family>/<artifact-role>
│   ├── evidence/        frozen review packages and preserved archive
│   └── figs/            curated figures referenced by reports
├── phases/
│   └── <phase>/
│       ├── configs/     phase-locked parameters only
│       ├── scripts/     phase-specific temporary or locked procedures
│       └── runs/        compact provenance receipts only
└── artifacts/
    └── manifests/       resolvers for payload bytes outside Git
```

Root build and operating files (`README.md`, `AGENTS.md`, `CLAUDE.md`, Docker, Compose,
requirements) are allowed because they govern the whole repository; they do not create another information owner.

## Flow

```text
research area -> experiment purpose -> run identity -> artifact role
      docs           docs/experiments      phases       report/table/metric
                                                     or external manifest
```

- Reusable code moves from a phase to `src/` or `scripts/` when another workstream can call it.
- A phase keeps a script only while its lock, queue, or procedure is specific to that phase.
- A result becomes a document only after promotion into `docs/experiments/`.
- Raw datasets, checkpoints, dense geometry, full render/image bundles, logs, and caches stay outside Git.

## Storage classes

| Class | Placement |
|---|---|
| A. regular Git | source, configs, scripts, tests, text, compact CSV/JSON/figures, receipts, manifests |
| B. selected Git LFS | only approved review-critical binary evidence that cannot remain small |
| C. external artifact storage + manifest | datasets, checkpoints, point clouds, meshes, full image/render bundles, immutable run archives |
| D. raw/generated/ignored | reproducible intermediates, caches, mutable logs, locks, temporary panels |

Historical paths remain evidence inside frozen receipts. Migration ledgers and artifact manifests resolve them; they are not templates for new files.
