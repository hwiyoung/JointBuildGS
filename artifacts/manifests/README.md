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

Cross-host task transfer uses:

- `schemas/two_host_handoff.schema.json` — the machine-readable Work Host/Experiment Host contract;
- `schemas/local_wip_snapshot.schema.json` — the required structure for a dirty-WIP
  recovery snapshot, including component hashes, path ledgers, archive inventory,
  and restore-rehearsal evidence;
- `templates/two_host_handoff.json` — a deliberately invalid-until-filled template. Set
  `template_only=false`, replace the base commit and scopes, and validate it before use.

Actual handoff receipts, snapshot manifests, and snapshot components are immutable
add-once task/run-specific files. Do not create a mutable global `current_handoff.json`.
One event commit may add files only inside its current handoff directory and must not
modify, delete, copy, or rename any existing handoff-subtree path.
Receipt paths are fixed to `handoffs/<handoff_id>/000-offered.json`,
`100-accepted.json`, `200-verified.json` or `200-blocked.json`, and
`300-closed.json`; a handoff ID has exactly one offered root.
