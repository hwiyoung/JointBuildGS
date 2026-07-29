# JointBuildGS repository structure after information-architecture migration

## Outcome

The **tracked control plane is organized** around one owner per information role. Verified documents, evidence packages, run receipts, environment records, compact result evidence, reusable experiment drivers, and tests were migrated with path ledgers and reference checks. No file was deleted, `.gitignore` was not changed, and no bulk research payload was modified.

This is not a claim that hundreds of GiB of local payload have been externalized. `data/`, generated run payloads, `results/`, and `fair-pilot/` remain explicit transition areas until an external artifact backend and immutable manifest workflow exist.

## Final owner tree

```text
JointBuildGS/
├── README.md                  # repository entry point and folder router
├── AGENTS.md / CLAUDE.md      # repository-wide scientific/operating rules
├── Dockerfile / compose       # reproducible execution environment entry points
│
├── src/                       # reusable imported implementation
├── configs/                   # versioned declarative parameters
├── scripts/                   # reproducible workflows and experiment drivers
│   └── experiments/           # reusable family-specific drivers
├── tools/                     # repository maintenance and inspection utilities
├── tests/                     # automated implementation/contract checks
│   └── experiments/           # promoted experiment-driver tests
│
├── docs/                      # durable human knowledge and promoted evidence
│   ├── README.md              # document router
│   ├── research/              # context, plans, preregistration, decisions, policy
│   ├── experiments/           # one landing page and evidence tree per family
│   ├── evidence/              # frozen reviewer/advisor evidence packages
│   ├── figs/                  # curated figures, not raw render sweeps
│   ├── archive/               # retained superseded/retracted material
│   └── catalog/               # generated inventory, lineage, contracts, migrations
│
├── phases/                    # lifecycle governance and execution provenance
│   ├── README.md
│   ├── RUN_CATALOG.csv
│   ├── p0-audit/              # frozen P0 rules and receipts/evidence exceptions
│   └── p2-gsjso/              # active P2 rules, issues, compact run receipts
│
├── artifacts/                 # absent until external backend approval
├── external/                  # conditional third-party source only
└── legacy/                    # conditional inactive reference-code quarantine
```

## Why every permanent folder exists

| Folder | Question it answers | Content that does not belong there |
|---|---|---|
| `src/` | What reusable method is imported? | CLI orchestration, run output, copied projects |
| `configs/` | With which explicit parameters was it run? | results, logs, secrets, checkpoints |
| `scripts/` | Which reproducible command produces the run/report? | hidden method implementation, generated output |
| `tools/` | Which utility maintains or inspects the repository? | canonical scientific workflow logic |
| `tests/` | Which executable assertions protect code and contracts? | full datasets or result archives |
| `docs/` | What should a researcher or reviewer read and cite? | raw logs, mutable state, checkpoints, render sweeps |
| `phases/` | Under which stage rules and provenance did a run occur? | duplicate reports, reusable code, bulk payloads |
| `artifacts/` | Where is an externally stored immutable payload resolved? | payload bytes themselves |

`docs/` therefore owns a promoted result as human evidence; `phases/` owns its execution identity and provenance. A report is stored once and linked from its run receipt.

## Applied migrations

The structure work is represented by 17 commits after the live pushed branch snapshot through `3888191`, with exact path maps in `docs/catalog/migrations/`.

| Migration family | Result |
|---|---|
| Boundary map | Documents and dedicated drivers promoted to canonical owners. |
| Research/document wave 1 | Verified research, experiment, and archive families organized. |
| E5 C001 | 242-file chain organized under family owners. |
| Environment and receipts | `env/versions.md` and 14 root run receipts promoted; tracked `env/` and `runs/` are empty. |
| Frozen evidence | Evidence-card and judgment-kit packages placed under `docs/evidence/`. |
| Compact results and nightly reports | Reviewed tracked evidence promoted to `docs/archive/`, `docs/experiments/`, and `docs/figs/`. |
| P0 G1 | Frozen review package promoted under `docs/evidence/p0_g1_20260613/`. |
| P2 reusable code | 64 driver/test paths promoted to `scripts/experiments/` and `tests/experiments/`; path contracts hardened. |
| Final docs-root waves | 59 reviewed ASCII/Unicode owner placements recorded; compatibility and locked inputs retained deliberately. |

No migration ledger authorizes deletion. A retained old path can be a required byte-identical compatibility mirror, not an accidental duplicate.

## `docs/` direct-file remainder

The physical `docs/` root now contains 70 files, down from more than 400 direct files. Every remainder has an explicit reason:

| Reason | Files |
|---|---:|
| `docs/README.md` entry point | 1 |
| Declared compatibility mirrors | 20 |
| Path-locked scientific inputs | 15 |
| Lineage or ownership holds requiring scientific review | 34 |

New documents must not expand this remainder. They go directly to `docs/research/`, `docs/experiments/<family>/`, `docs/evidence/`, or `docs/archive/`.

Four additional research documents remain at repository root because active scripts, configs, receipts, or locked protocols consume their exact root paths. They are compatibility inputs, not a pattern for new root documents.

## Transitional and local payload roots

| Root | Approximate local physical state at the transition audit | Tracked state after migration | Decision |
|---|---:|---|---|
| `data/` | 162 GiB | `.gitkeep` only | Ignored local dataset volume; class C after backend approval. |
| `results/` | 108 GiB | 311 compact/historical files remain | Mixed transition tree; move only reviewed families with writer and lineage checks. |
| `phases/` | 186 GiB | rules, phase exceptions, receipts, selected evidence | Keep control records; externalize/ignore bulk run payload by manifest later. |
| `fair-pilot/` | 2.2 GiB | 32 control files | Decompose only after embedded paths and its local payload contract are mapped. |
| `reports/` | 164 MiB | zero tracked files | Remaining untracked runtime state stays untouched; do not treat as canonical evidence. |
| `env/` | empty | zero tracked files | Migration complete; empty physical remnant retained because deletion was prohibited. |
| `runs/` | empty directory skeletons | zero tracked files | Migration complete; canonical receipts are in `phases/p2-gsjso/runs/`. |

Blindly moving these bytes to another repository folder would only rename the storage problem and could break scientific paths. The next storage migration starts by approving a backend, manifest schema, hydration command, checksum/retention rules, and one pilot artifact.

## Storage classes at this milestone

| Class | Current placement |
|---|---|
| A. regular Git | Code, configs, scripts, tests, research/control documents, compact evidence, manifests/receipts. |
| B. selected Git LFS | Proposed only for an explicit allowlist of curated binary evidence; LFS is not configured. |
| C. external artifact storage + manifest | Required future home for datasets, checkpoints, dense geometry, full image bundles, and immutable run archives; backend not yet selected. |
| D. raw/generated/ignored | Current local caches, mutable logs, rerunnable panels/renders, and most run payloads. |

## Push and clone boundary

Live read-only remote verification on 2026-07-30 found `origin/exp/fusion-w1` at `97f6b3ef3159360b88ba0b25cca4b280c14fdcb8`. Its pushed tree is:

- 6,016 files;
- 767,935,421 uncompressed blob bytes;
- 732.360 MiB logical checkout content.

At the pre-final-document checkpoint, local `3888191` was 17 commits ahead, with 6,158 files and 774,673,431 bytes (738.786 MiB). The information-architecture commits are local until an explicit push. Remote packed storage or transfer size is not the same as tree bytes and cannot be inferred from a tree listing.

The local `.git` directory measured 1,920,692,651 bytes (1.789 GiB); `git count-objects -vH` reported 3,560 loose objects / 247.21 MiB and 14,819 packed objects in 10 packs / 1.55 GiB. The last full payload scan remains 457.691 GiB excluding `.git`; this reorganization did not delete or mutate those payloads.

## Final recommendation

Choose **2. existing repo + partial clone/sparse checkout** for the control plane. There is no current single-blob emergency requiring history cleanup, while a new blob-filtered sparse checkout avoids hydrating unneeded tracked evidence. Sparse checkout is not an artifact manager, so class-C backend adoption remains the next storage milestone.

Do not create a separate ResearchControl repository merely to compensate for unclear folders: the owner map and catalogs now provide that control plane inside the existing repository. Reconsider a split only for real access-control, publication, or independent lifecycle requirements.
