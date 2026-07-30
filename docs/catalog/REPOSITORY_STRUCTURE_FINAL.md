# JointBuildGS repository structure after information-architecture migration

## Outcome

The **tracked control plane and bulk storage plane are now separated** around one owner per information role. Verified documents, evidence packages, run receipts, compact result evidence, reusable drivers, tests, and pilot controls were migrated with path ledgers and reference checks. No file was deleted, `.gitignore` was not changed, and no research payload byte was rewritten.

`STORAGE-IA-01` moved 428,296,653,718 bytes to the sibling `../JointBuildGS-artifacts` backend by same-device atomic rename. `data`, `results`, `reports`, `fair-pilot`, and P0 bulk data/runs are no longer Git information roots. Docker supplies compatibility mounts for historical runtime paths.

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
│   ├── experiments/           # family landing pages plus reports/tables/metrics/manifests/models
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
├── artifacts/                 # tracked external-payload manifests/resolvers
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

The structure work is represented by task-scoped commits after the live pushed branch snapshot, with exact path maps in `docs/catalog/migrations/`. Commit count is intentionally not treated as a structural invariant.

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
| Final docs-root waves | 93 reviewed owner placements recorded; two in-flight path locks retained deliberately. |

No migration ledger authorizes deletion. A retained old path can be a required byte-identical compatibility mirror, not an accidental duplicate.

## `docs/` direct-file remainder

The physical `docs/` root now contains three files, down from more than 400 direct files. Every remainder has an explicit reason:

| Reason | Files |
|---|---:|
| `docs/README.md` entry point | 1 |
| Active staged boundary-map v2 input | 1 |
| Current staged Fusion regression input | 1 |

New documents must not expand this remainder. Former compatibility copies were preserved without deletion under `docs/archive/compatibility/root-mirrors/`; active clean consumers now use canonical owner paths. The two direct CSVs remain only because changing the user's staged files would violate the working-tree boundary.

## Physical payload relocation

| Former root | Bytes moved | Final control-plane owner | Runtime resolution |
|---|---:|---|---|
| `data/` | 173,592,976,197 | `artifacts/manifests/` | Docker compatibility mount |
| `results/` | 115,693,750,893 | 311 compact files split into family reports/tables/metrics/manifests/models, phase receipts, figures, and configs | Docker compatibility mount |
| `reports/` | 171,621,547 | artifact manifest only | Docker compatibility mount |
| `fair-pilot/` | 2,279,659,141 | config/scripts/docs/phase receipt split by role | Docker compatibility mount |
| `phases/p0-audit/data` | 72,627,527,687 | artifact manifest only | Docker compatibility mount |
| P0 bulk runs | 63,931,118,253 | 189 compact tracked receipt files remain in phase | Docker compatibility mount |

`env/` and root `runs/` had no files and were moved as empty historical placeholders. The only remaining large in-repository workspace is active `phases/p2-gsjso/runs/`; it is intentionally deferred until the current Fusion-W1 run closes.

## Storage classes at this milestone

| Class | Current placement |
|---|---|
| A. regular Git | Code, configs, scripts, tests, research/control documents, compact evidence, manifests/receipts. |
| B. selected Git LFS | Proposed only for an explicit allowlist of curated binary evidence; LFS is not configured. |
| C. external artifact storage + manifest | Sibling local backend currently holds datasets, checkpoints, dense geometry, image bundles, and historical run workspaces; it is organized but is not yet a durable backup. |
| D. raw/generated/ignored | Mutable caches/logs and active P2 runtime material; promote or externalize at run closeout. |

## Push and clone boundary

Live read-only remote verification on 2026-07-30 found `origin/exp/fusion-w1` at `97f6b3ef3159360b88ba0b25cca4b280c14fdcb8`. Its pushed tree is:

- 6,016 files;
- 767,935,421 uncompressed blob bytes;
- 732.360 MiB logical checkout content.

At the pre-final-document checkpoint, local `3888191` was 17 commits ahead, with 6,158 files and 774,673,431 bytes (738.786 MiB). The information-architecture commits are local until an explicit push. Remote packed storage or transfer size is not the same as tree bytes and cannot be inferred from a tree listing.

The pre-migration local `.git` directory measured 1,920,692,651 bytes (1.789 GiB). After physical relocation, the main working tree excluding `.git` is approximately 59 GiB, dominated by the active P2 workspace; the moved 428,296,653,718 bytes remain on the same filesystem in `../JointBuildGS-artifacts`.

## Final recommendation

Choose **2. existing repo + partial clone/sparse checkout** for the control plane. There is no current single-blob emergency requiring history cleanup, while a new blob-filtered sparse checkout avoids hydrating unneeded tracked evidence. Sparse checkout is not an artifact manager, so durable off-machine replication of the current class-C workspace remains the next storage milestone.

Do not create a separate ResearchControl repository merely to compensate for unclear folders: the owner map and catalogs now provide that control plane inside the existing repository. Reconsider a split only for real access-control, publication, or independent lifecycle requirements.
