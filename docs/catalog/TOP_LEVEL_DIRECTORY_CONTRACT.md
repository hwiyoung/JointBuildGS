# JointBuildGS top-level directory contract

## Status

This contract defines why each top-level directory may exist and which information it owns. The control-plane migrations recorded under `docs/catalog/migrations/` have now applied this contract to verified document, evidence, receipt, script, and test families.

The contract does not authorize deletion, `.gitignore` changes, artifact upload, Git LFS conversion, or history rewriting. The 2026-07-30 storage migration used byte-preserving same-filesystem moves into a sibling local artifact workspace and recorded every bulk root in a manifest.

## Admission rule

A top-level directory is justified only when it owns a stable kind of information that no other top-level directory owns. Convenience, one experiment, one tool, or one report is not enough reason to create another root.

Every permanent root must answer all four questions:

1. What unique information does it own?
2. What must never be stored there?
3. Who or what creates and validates its contents?
4. What is the retention and Git policy?

## Permanent repository roots

The target control plane has eight permanent top-level directories.

| Root | Why it exists | Owns | Must not own | Lifecycle and Git policy |
|---|---|---|---|---|
| `src/` | The research method needs one importable implementation, independent of any particular run. | Reusable GS-JSO Stage 2/3 libraries, models, losses, data interfaces, exporters. | CLI orchestration, experiment parameters, generated code, results, copied third-party projects. | Regular Git; reviewed and tested like product code. |
| `configs/` | Scientific and operational parameters must be explicit, diffable, and reusable without editing code. | Declarative YAML/JSON/TOML configs and schemas; family subdirectories are allowed. | Checkpoints, logs, computed metrics, secrets, workstation-only absolute paths, duplicate config copies inside runs. | Regular Git. A run receipt references the exact config path and content hash. |
| `scripts/` | Reproducible workflows need stable command-line entry points that connect configs to `src/`. | Training, evaluation, conversion, reporting, and repository inventory drivers. | Reusable method implementations that should be imported from `src/`; hidden scientific constants; one-off shell history; generated outputs. | Regular Git; execution that affects research evidence must be recorded by a run receipt. |
| `tools/` | Repository maintenance and human inspection need utilities that are not part of the scientific pipeline. | Catalog checkers, viewers, format inspectors, developer maintenance utilities. | Scientific method logic, canonical experiment drivers, experiment-specific result trees. | Regular Git. If a tool changes a scientific result, it must be promoted to `scripts/` or `src/` and covered by provenance. |
| `tests/` | Claims about code and contracts need executable regression checks. | Unit, integration, schema, lineage, and reproducibility tests plus small deterministic fixtures. | Full datasets, checkpoints, large images, result archives, manual QA reports. | Regular Git; fixtures follow explicit size gates. Test outputs are ephemeral. |
| `docs/` | Humans need one authoritative knowledge and promoted-evidence surface. | Research context, plans, preregistration, decisions, canonical experiment reports, compact evidence tables, curated figures, review packages, document lineage. | Raw logs, mutable run state, checkpoints, full render sweeps, duplicate run receipts, caches. | Text and compact evidence in regular Git; selected binary evidence may use approved LFS later. One canonical document per declared purpose. |
| `phases/` | The project has governed research stages with different rules and must preserve which run occurred under which stage contract. | Phase orientation/rules and compact run receipts: commit, config reference, container, inputs, outputs, status, exceptions, retraction/supersession links. | Canonical research reports, reusable source code, canonical config copies, raw payloads, large generated result trees. | Regular Git for rules and compact receipts. Phase closure freezes the ledger but does not duplicate its reports. |
| `artifacts/` | Git needs stable resolvers for large or access-controlled evidence stored elsewhere. | Small manifests containing artifact ID, URI/path, bytes, hash, producer, config, Git commit, access class, retention, and CRS. | Checkpoint, dataset, point-cloud, mesh, image-bundle, or archive bytes themselves. | Manifests in regular Git; payloads currently use the sibling local workspace and still need durable backup. |

## Why `docs/` and `phases/` are both necessary

They answer different questions:

- `docs/`: **What did the research establish, and what evidence should a reader use?**
- `phases/`: **Under which rules, code, configuration, environment, and run did that evidence arise?**

The same report must not be stored in both places. A promoted report lives in `docs/`; its run receipt in `phases/` links to it. The report links back to the run ID.

```text
configs/ + scripts/ + src/
             |
             v
phases/<phase>/runs/<run_id>/receipt
             |                         \
             | promotes                 \ resolves large payload
             v                           v
docs/experiments/<family_id>/       artifacts/manifests/<artifact_id>
report + compact tables + figures        -> external object storage
```

An execution result is routed by role:

| Result kind | Owner |
|---|---|
| Human interpretation, final summary, approved table, curated figure | `docs/` |
| Run identity, exact code/config/container/input/output linkage, failure/retraction state | `phases/<phase>/runs/<run_id>/` |
| Dataset, checkpoint, dense point cloud, mesh, full image/render bundle, immutable run archive | external storage referenced by `artifacts/` |
| Cache, mutable log, PID/lock, temporary panel, reproducible intermediate | ignored local workspace; no durability promise |

## Boundary tests

Use the first matching question when placing a new file:

| Question | Destination |
|---|---|
| Is it imported as part of the active method? | `src/` |
| Is it a declarative parameter set consumed by code? | `configs/` |
| Is it an executable research workflow or report generator? | `scripts/` |
| Is it a maintenance, inspection, or developer utility? | `tools/` |
| Is it an automated assertion or small fixture? | `tests/` |
| Is it intended for a human reader as durable research knowledge or promoted evidence? | `docs/` |
| Is it a phase rule or compact execution/provenance receipt? | `phases/` |
| Is it a resolver for externally stored payload bytes? | `artifacts/` |
| Is it raw/mutable/generated payload rather than one of the above? | External or ignored workspace, not a new Git root. |

Ambiguous cases must be resolved by ownership, not file extension. A JSON file can be a config, run receipt, evidence table, or artifact manifest depending on its role.

## Conditional top-level exceptions

These roots may remain only while their special boundary is real and documented. They are not general-purpose destinations.

| Root | Conditional reason | Required boundary | Current direction |
|---|---|---|---|
| `external/` | Vendored or submodule-managed third-party source may need isolation from project code. | Upstream URL/version, license, local modifications, and update procedure must be recorded. Project-owned code is forbidden. | Currently has no indexed files. Do not populate it without an approved dependency contract. |
| `legacy/` | Inactive historical/reference implementation may need to remain available without being mistaken for active `src/`. | `README.md` must state why it is retained, whether live code imports it, and the replacement path. New feature work is forbidden. | Seven indexed files currently form a PlanarSplat reference quarantine. Retention or later external archiving needs separate review. |

Repository-wide instructions retain `external/` and `legacy/` as conditional source-code boundaries. Historical `results/` paths are runtime compatibility mounts only; compact evidence now has role-specific owners and bulk bytes live in the sibling artifact workspace.

## Runtime compatibility roots

`data/`, `results/`, `reports/`, and `fair-pilot/` may appear as empty host mount points while Docker is running. They own no Git information. Docker mounts the corresponding paths from `../JointBuildGS-artifacts`; P0 bulk data and historical runs use the same compatibility mechanism. Root `env/` and `runs/` contain no tracked information.

Local tool-state directories such as `.agents/`, `.claude/`, and `.codex/` are not research information roots. They must not become owners of source, evidence, run receipts, or artifacts.

## Root files, not directories

Some repository-wide concerns are clearer as a small set of root files rather than another directory:

- `README.md`: repository entry point;
- `AGENTS.md` and `CLAUDE.md`: operating rules;
- `Dockerfile`, Compose files, requirements/lock files: development and runtime environment entry points;
- license and citation files when added.

A new top-level directory must not be created merely to hold one such file.

## Applied consequences and remaining gates

1. Verified reusable P2 drivers and tests now live under root `scripts/experiments/` and `tests/experiments/`; scientifically locked or still phase-specific implementations remain phase-local.
2. `boundary_map` and later document/evidence families were moved only with old-to-new path ledgers and reference validation.
3. Root `env/` and `runs/` no longer own tracked information; tracked `reports/` material was promoted to its document/figure owners.
4. `results/`, local `reports/`, and `fair-pilot/` were split by role; their former runtime paths are compatibility mounts, not templates for new roots.
5. Historical bulk payload is in the sibling artifact workspace with a checked manifest. Active P2 runtime payload remains phase-local until the current Fusion work closes.

The resulting folder state and deliberate exceptions are recorded in [`REPOSITORY_STRUCTURE_FINAL.md`](REPOSITORY_STRUCTURE_FINAL.md).
