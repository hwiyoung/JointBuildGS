# JointBuildGS top-level directory contract

## Status

This contract defines why each top-level directory may exist and which information it owns. It is the prerequisite for document-family review and later path migration.

It does not move or delete current files, change `.gitignore`, rewrite references, upload artifacts, configure Git LFS, or alter Git history. Existing paths remain authoritative until a separate migration is approved.

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
| `artifacts/` | Git needs stable resolvers for large or access-controlled evidence stored elsewhere. | Small manifests containing artifact ID, immutable URI, bytes, hash, producer, config, Git commit, access class, retention, and CRS. | Checkpoint, dataset, point-cloud, mesh, image-bundle, or archive bytes themselves. | Manifests in regular Git; payloads in approved external storage. The directory is created only when the first backend and manifest are approved. |

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

The repository-wide instructions currently freeze several existing root paths, including `external/`, `legacy/`, and `results/`. This contract does not override that rule or authorize movement; a later migration must update the governing instructions explicitly.

## Current non-target and transitional roots

Snapshot counts below are indexed-file counts observed during `DOC-IA-01A`; they are time-specific and do not include ignored payload volume.

| Current root | Indexed files | Why it exists today | Target disposition, without action in this task |
|---|---:|---|---|
| `data/` | 1 | Local dataset/work-volume mount placeholder. | Not a durable Git information root. Raw inputs become external class C; local hydration remains a workspace concern. |
| `env/` | 1 | A root-level `versions.md` records environment information. | Environment build definitions stay in root build files or an approved config namespace; immutable runtime versions belong in run receipts. Review before any move. |
| `fair-pilot/` | 32 | A self-contained pilot copied configs, scripts, docs, and run records under one root. | Decompose by role into the permanent roots after lineage review; do not create more project-shaped roots. |
| `reports/` | 9 | Nightly post-analysis mixed final prose, figures, manifests, and runtime material. | Promote durable report/evidence to `docs/`; route payloads to C/D; retire the root only after exact mapping. |
| `results/` | 323 | Historical experiment trees combine reports, metrics, configs, viewers, and generated payloads. | Split by role: promoted evidence to `docs/`, receipts to `phases/`, payloads to C/D. Current root rule prohibits immediate movement. |
| `runs/` | 14 | Older root-level run records predate the phase ledger convention. | Map compact receipts into the owning phase; externalize/ignore payloads after dependency review. |

Local tool-state directories such as `.agents/`, `.claude/`, and `.codex/` are not research information roots. They must not become owners of source, evidence, run receipts, or artifacts.

## Root files, not directories

Some repository-wide concerns are clearer as a small set of root files rather than another directory:

- `README.md`: repository entry point;
- `AGENTS.md` and `CLAUDE.md`: operating rules;
- `Dockerfile`, Compose files, requirements/lock files: development and runtime environment entry points;
- license and citation files when added.

A new top-level directory must not be created merely to hold one such file.

## Consequences for the next tasks

1. Correct the target tree so `phases/<phase>/` no longer owns duplicate `configs/`, `scripts/`, or canonical `docs/` in the long-term model.
2. Review one experiment family, beginning with `boundary_map`, using the boundary tests above.
3. Produce an old-to-new mapping preview that separates report, receipt, and payload before any move.
4. Treat `results/`, `reports/`, `runs/`, and `fair-pilot/` as migration inputs, not templates for new top-level roots.

No physical migration is authorized by this contract.
