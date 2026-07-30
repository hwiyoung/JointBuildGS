# Local artifact retention cleanup — 2026-07-30

## Outcome

The reviewed cleanup removed `78,521,909,700` logical bytes (`73.13 GiB`) and
`307` files from the sibling `JointBuildGS-artifacts` workspace.  Empty and
generated layout cleanup also removed 2,118 directory entries.  Apparent
workspace size changed from `490,795,440,947` bytes to `412,264,843,631` bytes.

The immutable plan and sealed receipt are:

- `artifacts/manifests/local_artifact_retention_plan_20260730.json`
- `artifacts/manifests/local_artifact_retention_receipt_20260730.json`

The cleanup did not rewrite Git history, edit `.gitignore`, delete unique raw
data, delete final experiment results, or touch active Fusion payloads.

## Deleted scope

| Class | Count | Logical bytes | Deletion gate |
|---|---:|---:|---|
| MatrixCity source archives | 21 files | 73,471,507,963 | local SHA-256 equals the official Hugging Face LFS OID at pinned revision `22237509a7a16d5c0136b58b39597629a63b338d`; extracted copies and live depth/normal links remain |
| Historical intermediate checkpoints | 29 files | 5,028,520,496 | exact path is not referenced by current tracked or untracked text; every affected checkpoint directory retains its latest step and `final.pt` |
| Exact duplicate evidence, bytecode/download caches, retired placeholders | 257 files | 21,881,241 | canonical evidence SHA-256 matches; remaining content is generated or empty |

The MatrixCity archives are recoverable from the pinned official dataset tree:
`https://huggingface.co/datasets/BoDai/MatrixCity/tree/22237509a7a16d5c0136b58b39597629a63b338d`.
The plan records the per-file URL, byte count, and SHA-256.

## Retained scope

- all extracted MatrixCity images, depth, normal, semantic, sparse, and point-cloud working data;
- all unique P0 raw inputs, derived P0 work, and P0 run payloads;
- all completed Pilot 1-wave retained full-state checkpoints, geometry NPZ files, and prediction/receipt pack;
- all current Fusion W1 payloads and the existing staged, unstaged, and untracked Fusion work;
- all final checkpoints and the latest step checkpoint in every affected historical run;
- all checkpoint paths referenced by current documentation, manifests, catalogs, or run receipts;
- the nightly RV1 report and its cache, until its repo-relative source resolver is corrected;
- migration TSV/CSV/audit records, the referenced legacy source snapshot, and the unique Fusion Roofer runtime log.

## Post-cleanup verification

- planned targets remaining: `0 / 66`;
- retained latest checkpoints: `76 / 76`;
- retained MatrixCity extracted counterparts: `21 / 21`;
- retained canonical evidence files: `18 / 18`;
- MatrixCity source archives remaining: `0`;
- broken MatrixCity depth/normal links: `0`;
- active `phase-payloads/p2-gsjso/runs/fusion_w1` was outside the deletion plan.

## Next reduction priority

The workspace is still about `412.3 GB`, so this is a first retention pass, not
the final storage design.  The next useful review is run-level compaction of
`phase-payloads/p0-audit/runs` and derived `phase-payloads/p0-audit/data/work`.
That review must first identify a compact no-recompute recovery pack for each
canonical P0 result.  It must not delete the raw P0 input set merely because the
source URLs are available.  Active Fusion compaction remains deferred until the
phase is closed and a run-specific retention plan preserves resume state and
canonical qualitative evidence.
