# Repository structure after semantic relocation

## Status

The repository control plane now has seven information roots: `src`, `configs`, `scripts`,
`tests`, `docs`, `phases`, and `artifacts`. `tools`, `external`, and `legacy` no longer own tracked
files. Former payload roots and inactive material were preserved in `../JointBuildGS-artifacts` with
manifests; no history rewrite, `git clean`, `git gc`, or content-transforming cleanup was used.

## Applied ownership

| Owner | Current organization |
|---|---|
| `src/` | `stage2`, `stage3`, `geospatial`, reusable `pipelines`, and `apps` |
| `configs/` | input/alignment, mutual loss, E5/C001, pilots, and repository controls |
| `scripts/` | input/alignment, mutual loss, boundary/robustness, E5/C001, pilots, Stage 3, evaluation, inspection, repository |
| `tests/` | reusable code and workstream contracts; Fusion tests are grouped under `tests/fusion_w1` |
| `docs/` | research, purpose-grouped experiments, evidence/archive, and curated figures |
| `phases/` | P0 and P2 rules plus phase-specific locks, procedures, and compact receipts |
| `artifacts/` | manifests resolving external payload and quarantine locations |

`docs/experiments/` uses `input-and-alignment`, `joint-optimization`, `citygml-readout`,
`evaluation`, `pilots`, and `research-operations` as reader-facing purposes. `phases/p2-gsjso/runs/`
uses matching workstream groups rather than a flat list of run IDs.

## Preservation boundary

- Raw/generated P0, P2, and Fusion payloads were moved by same-filesystem rename and verified without changing bytes.
- Exact duplicate figures, inactive legacy/external material, caches, and empty layouts have reversible quarantine manifests.
- Frozen manifests and run receipts retain historical paths and scientific hashes.
- Current user Fusion additions and staged/unstaged states remain outside structural commits.

## `.gitignore` correction

Commit `fa027a8` accidentally changed viewer ignore paths despite the audit constraint. Because history
rewrite is forbidden, the final relocation restores `.gitignore` byte-for-byte to its pre-audit state in
a normal corrective commit and records the incident here. The restored historical rules may mention old
paths; that is explicit policy debt and not permission to edit the file again during this audit.

## Navigation

- Directory contract: [`TOP_LEVEL_DIRECTORY_CONTRACT.md`](TOP_LEVEL_DIRECTORY_CONTRACT.md)
- Target architecture: [`TARGET_INFORMATION_ARCHITECTURE.md`](TARGET_INFORMATION_ARCHITECTURE.md)
- Canonical document map: [`CANONICAL_MAP.md`](CANONICAL_MAP.md)
- Artifact resolvers: [`../../../artifacts/manifests/`](../../../artifacts/manifests/)
