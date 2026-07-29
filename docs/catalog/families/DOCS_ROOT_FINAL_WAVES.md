# Final docs-root family waves

## Outcome

`DOC-IA-09` moved 51 clear ASCII-named supporting files (31 families, 414,528 source bytes) from the `docs/` root into experiment, evidence, research, or archive owners. Fifty-two reviewed active reference files were updated; 17 historical receipt/manifest references were deliberately preserved and resolve through the migration ledger.

`DOC-IA-10` reviewed the 19 non-ASCII direct files that an earlier quoted-path enumeration had missed. Eight received owner paths: three were moved, while five path/SHA-bound documents were copied to their owner families and retained byte-identically at the old paths. One previously declared preregistration compatibility mirror stays at root. Ten Unicode documents remain lineage holds.

Exact paths and target hashes are recorded in:

- `docs/catalog/migrations/DOCS_ROOT_FAMILIES_WAVE2_PATHS.csv`
- `docs/catalog/migrations/DOCS_ROOT_UNICODE_PATHS.csv`

## Deliberate direct-file remainder

After these waves, the physical `docs/` root has 70 files, divided by reason:

| Reason | Files | Why direct placement remains |
|---|---:|---|
| Entry point | 1 | `docs/README.md` is the documentation router. |
| Declared compatibility mirrors | 20 | Active or frozen exact-path/SHA consumers still require the old path. |
| Path-locked scientific inputs | 15 | S3B0 (9), S3A′ (3), and Primary4 (3) locks cannot be rewritten without changing protocol bytes. |
| Lineage/ownership holds | 34 | Canonical, superseded, prompt/receipt, or cross-family ownership remains scientifically ambiguous. |

This remainder is an explicit compatibility and review surface, not an invitation to add new root documents. New documents go directly to `docs/research/`, `docs/experiments/<family>/`, `docs/evidence/`, or `docs/archive/`.

## Invariants

- No frozen run receipt, historical manifest, original data, or experiment result was rewritten.
- Compatibility targets and their retained old paths have equal SHA-256 values.
- The 15 locked inputs and 34 lineage holds were not moved by filename inference.
- The generated catalog reports remaining broken or ambiguous references; it does not silently choose a scientific canonical result.
