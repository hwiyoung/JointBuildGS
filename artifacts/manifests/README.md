# Artifact manifests

Manifests in this directory resolve payloads outside the Git repository. Each
manifest records the source path, backend URI, measured size and file count,
and the integrity evidence available for the move.

Directory hashes were not invented after the fact. The 2026-07-30 migration
used same-device atomic renames and verified unchanged device/inode identities;
existing per-file hashes inside scientific receipts remain authoritative.
