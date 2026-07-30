# Transitional-root migration map

Review date: 2026-07-29

The repository previously had root-level `env/` and `runs/` control-plane files. Their roles are now assigned to permanent owners:

- repository-wide environment knowledge → `docs/research/reproducibility/`;
- P2 execution receipts → `phases/p2-gsjso/runs/<run_id>/`.

`ROOT-IA-01` moved one environment record and 14 `versions.txt` receipts byte-for-byte. Producer defaults now write to the phase ledger, so routine reruns do not recreate root `runs/`. Exact old/new paths and SHA-256 values are in [`ROOT_ENV_RUN_RECEIPTS_PATHS.csv`](../migrations/ROOT_ENV_RUN_RECEIPTS_PATHS.csv).

`DOC-IA-ARCHIVE-01` and `DOC-IA-REPORT-01` initially promoted 21 compact tracked files from `results/` and `reports/`. `STORAGE-IA-01` later moved the bulk payloads into the sibling local artifact workspace, and `RESULT-IA-02` split the remaining compact result snapshots by role. Former root paths now exist only as Docker compatibility mounts.
