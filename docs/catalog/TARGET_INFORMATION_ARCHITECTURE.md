# JointBuildGS target information architecture

## Status and boundary

This document defines the target organization for later review and migration. It does not authorize or perform file moves, deletions, bulk reference rewrites, `.gitignore` changes, artifact uploads, Git LFS conversion, or history rewriting.

The reason and admission rule for every top-level directory are authoritative in [`TOP_LEVEL_DIRECTORY_CONTRACT.md`](TOP_LEVEL_DIRECTORY_CONTRACT.md). This document applies that contract to the internal tree.

The current paths remain valid until a separate family-scoped migration is approved and verified. The catalogs beside this document describe the current state; this document describes the intended state.

The catalog's own generated files and navigation/control documents are excluded from its row set. This prevents self-referential size, Git-state, and commit-history churn while keeping the research-document inventory reproducible after commit.

## Design rules

1. Keep one obvious entry point for the repository, documents, phases, and each experiment family.
2. Separate durable research knowledge, experiment evidence, execution receipts, and bulk payloads.
3. Give every versioned document a stable `family_id`; a filename alone must not determine lineage.
4. Allow at most one approved `canonical` document for a `canonical_for` purpose.
5. Preserve superseded and retracted material with an explicit status and successor link. Do not silently overwrite or delete it.
6. Store a report once. Run records and indexes link to it instead of copying it into several locations.
7. Keep root GS-JSO implementation paths where the repository rules currently require them.

## Target tree

```text
JointBuildGS/
  README.md                     # repository entry point
  AGENTS.md / CLAUDE.md         # repository-wide operating rules
  src/                          # GS-JSO implementation; remains at root
  configs/                      # reusable implementation/experiment configs
  scripts/                      # reproducible repository-wide drivers
  tools/                        # maintenance and inspection tools
  tests/                        # automated checks

  docs/
    README.md                   # research-document entry point
    research/                   # durable context, plans, preregistration, decisions, policies
    experiments/
      <family_id>/
        README.md               # the family landing page and approved canonical map
        reports/                # narrative reports and review notes
        tables/                 # compact CSV/JSON evidence tables
        manifests/              # provenance and external-artifact manifests
    figs/
      <family_id>/              # curated figures only; no raw render sweeps or caches
    evidence/
      <review_package_id>/      # frozen advisor/reviewer evidence packages
    archive/
      <family_id>/              # superseded/retracted documents retained with lineage
    catalog/                    # generated inventory and governing structure

  phases/
    README.md                   # phase and run entry point
    RUN_CATALOG.csv             # generated run-level catalog
    <phase_id>/
      README.md                 # phase orientation
      AGENTS.md / CLAUDE.md     # phase rules
      runs/
        <YYYYMMDD_run_id>/      # compact immutable execution/provenance receipt

  artifacts/
    manifests/
      <artifact_id>.yaml        # tracked resolver for externally stored class-C payloads

  external/                     # conditional: documented third-party source only
  legacy/                       # conditional: inactive reference-code quarantine only
```

`artifacts/manifests/` and `docs/evidence/` are target paths only; they are not created by this task. External payload bytes do not live below `artifacts/`.

## Ownership boundaries

| Information | Owner path | Contents | Default storage class |
|---|---|---|---|
| Research contract | `docs/research/` | context, plan, preregistration, decisions, storage policy | A |
| Experiment family | `docs/experiments/<family_id>/` | family index, reports, compact tables, manifests | A |
| Curated visual evidence | `docs/figs/<family_id>/`, later review packages | approved final figures only | selected B |
| Execution receipt | `phases/<phase>/runs/<run_id>/` | config path/hash, commit/container receipt, aggregate status, issues, artifact references | A |
| Raw or irreplaceable payload | external storage + `artifacts/manifests/` | datasets, checkpoints, dense geometry, full-resolution imagery, archives | C |
| Mutable/generated runtime state | ignored work/run locations | caches, logs, temporary panels, rerunnable intermediate output | D |

The A-D meanings are defined in `docs/research/PROPOSED_STORAGE_POLICY.md`. Existing files are not reclassified or migrated merely because this target is documented.

## Document metadata contract

New canonical or versioned Markdown documents should carry machine-readable front matter. Existing files receive inferred catalog fields until they are reviewed; this task does not insert front matter into them.

```yaml
---
doc_id: boundary-map-summary-v4
family_id: boundary_map
document_type: report
version: v4
status: canonical
canonical_for: boundary_map_summary
supersedes:
  - docs/archive/boundary_map/boundary-map-summary-v3.md
derived_from:
  - phases/p2-gsjso/runs/20260719_boundary_map_v3/manifest.json
run_ids:
  - 20260719_boundary_map_v3
artifact_ids: []
---
```

Allowed reviewed statuses are:

| Status | Meaning |
|---|---|
| `canonical` | Approved current document for one declared purpose. |
| `supporting` | Valid supporting evidence, but not the entry point or final authority. |
| `superseded` | Retained history with an explicit successor. |
| `retracted` | Retained but prohibited as active evidence; reason must be recorded. |
| `draft` | Work in progress that is not an approved source. |
| `temporary` | Short-lived coordination material with an owner/review date. |
| `orphan` | No established owner, lineage, or inbound reference; review required. |

Generated inventory values ending in `_candidate` are not approved statuses. They are review prompts derived from filenames, paths, links, or Git history.

## Version and lineage policy

- A `family_id` is stable across versions and file moves.
- `version` records document evolution; dates record events. They are not interchangeable.
- `supersedes` means the newer document replaces the older document for the same declared purpose.
- `derived_from` records provenance and does not make the source obsolete.
- `references` is a navigational dependency only.
- `retracted` never becomes `superseded` merely because a newer file exists.
- Names such as `final`, `latest`, `new`, `tmp`, or an unqualified `v2` do not establish canonical status.
- A family landing page lists the approved canonical report, supporting tables/manifests/figures, run IDs, and retained predecessors.

## Run contract

Every future run directory should have one compact tracked receipt containing at least:

- run ID and phase;
- Git commit and dirty-state statement;
- script and config paths;
- container image tag and digest;
- input artifact IDs and immutable hashes where applicable;
- output artifact IDs or paths;
- status, exceptions, and retraction/supersession links;
- CRS for geospatial outputs.

Large payloads remain class C or D. A run directory is not considered documented merely because generated files exist on disk.

## Migration order

1. Approve the top-level directory contract.
2. Generate and review the current document/run inventory.
3. Approve canonical entries and unresolved lineage one family at a time.
4. Pilot `boundary_map`, because it spans reports, tables, manifests, figures, scripts, and runs across several versions.
5. Produce an exact old-to-new path manifest and reference rewrite preview for that family.
6. Move only the approved pilot in a separate commit, run link/provenance checks, and obtain human review.
7. Repeat by family; consolidate versioned evidence-package directories only after their canonical contents are agreed.
8. Adopt external artifact storage and selected LFS in separate policy tasks.

No physical migration step is executed by `DOC-IA-01` or `DOC-IA-01A`.
