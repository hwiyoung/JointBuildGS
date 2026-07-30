# Artifact manifests

Manifests in this directory resolve payloads outside the Git repository. Each
manifest records the source path, backend URI, measured size and file count,
and the integrity evidence available for the move.

Directory hashes were not invented after the fact. The 2026-07-30 migration
used same-device atomic renames and verified unchanged device/inode identities;
existing per-file hashes inside scientific receipts remain authoritative.

Reviewed local deletion is recorded separately from relocation. A cleanup is
complete only when an immutable `*_plan_*.json` has been applied and its paired
`*_receipt_*.json` verifies zero remaining targets plus all retained gates.

Fusion W1 uses three linked manifests:

- `fusion_w1_local_wip_snapshot_20260730.json` preserves the original dirty checkout for recovery;
- `fusion_w1_receipt_source_lock_20260730.json` binds completed receipts to 40 exact historical source files;
- `fusion_w1_completed_visuals_20260730.json` rehashes 45 declared external outputs without promoting them;
- `fusion_w1_wip_disposition_20260730.json` records the final technical disposition and exclusions.
