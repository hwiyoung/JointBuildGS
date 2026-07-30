# Final docs-root family waves

## Outcome

`DOC-IA-09` moved 51 clear ASCII-named supporting files (31 families, 414,528 source bytes) from the `docs/` root into experiment, evidence, research, or archive owners. Fifty-two reviewed active reference files were updated; 17 historical receipt/manifest references were deliberately preserved and resolve through the migration ledger.

`DOC-IA-10` reviewed the 19 non-ASCII direct files that an earlier quoted-path enumeration had missed. Eight received owner paths: three were moved, while five path/SHA-bound documents were copied to their owner families and retained byte-identically at the old paths. One previously declared preregistration compatibility mirror stays at root. Ten Unicode documents remain lineage holds.

Exact paths and target hashes are recorded in:

- `docs/research/repository/migrations/DOCS_ROOT_FAMILIES_WAVE2_PATHS.csv`
- `docs/research/repository/migrations/DOCS_ROOT_UNICODE_PATHS.csv`

## Final direct-file remainder

Follow-up migrations routed the 34 lineage holds, the 15 locked inputs, and 19 clean compatibility copies to explicit owners without deleting a byte. The physical `docs/` root now has three files:

| File | Why direct placement remains |
|---|---|
| `README.md` | Documentation router. |
| `boundary_map_v2_ladder.csv` | The user's current staged Fusion workflow names this exact source path. |
| `regression_input_snapshot.csv` | The user's current staged Fusion workflow names this exact input path. |

Former root copies are preserved under `docs/evidence/archive/compatibility/root-mirrors/`. New documents go directly to `docs/research/`, `docs/experiments/<family>/`, `docs/evidence/`, or `docs/evidence/archive/`.

## Invariants

- No frozen run receipt, historical manifest, original data, or experiment result was rewritten.
- Compatibility targets and their retained old paths have equal SHA-256 values.
- Every later move was recorded by an explicit path/SHA ledger; no scientific content was inferred or rewritten.
- The generated catalog reports remaining broken or ambiguous references; it does not silently choose a scientific canonical result.
