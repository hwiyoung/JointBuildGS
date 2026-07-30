# Evidence-package map

Review date: 2026-07-29  
Migration: `DOC-IA-07`

The four former top-level package directories under `docs/` are now version-separated owners under `docs/evidence/`. No versions were merged or deleted.

| Package | Files | Bytes | Status |
|---|---:|---:|---|
| `evidence_cards_v1` | 18 | 6,587,724 | historical frozen |
| `evidence_cards_v2` | 43 | 23,676,712 | historical frozen |
| `evidence_cards_v3` | 49 | 36,937,952 | supporting frozen |
| `judgment_kit_v4` | 47 | 49,189,407 | canonical candidate frozen |

All 157 payload files retain their pre-move SHA-256 and total 116,391,795 bytes. V3 and v4 manifests retain embedded historical paths; current generators use the new package roots. Repository-local compatibility copies were unnecessary because no tracked config, test, or frozen run receipt binds these package paths or hashes.
