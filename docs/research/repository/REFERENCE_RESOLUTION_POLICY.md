# Document reference resolution policy

`DOCUMENT_REFERENCE_RESOLUTIONS.csv` is the exact sidecar review for the 227
Markdown links and embeds that remained unresolved after the 2026-07-30 semantic
relocation inventory.  It changes no measurement, result, frozen evidence byte,
or historical path string.

## Reviewed classes

| Class | Count | Meaning | Action |
|---|---:|---|---|
| `deterministic_current_path` | 55 | The exact current Git target exists. | Repair the active document link. |
| `external_artifact` | 62 | The exact payload exists under the local artifact backend. | Resolve as `artifact://JointBuildGS/...`; remote Work must not assume availability. |
| `historical_migration` | 23 | A frozen source preserves its historical path text. | Keep source bytes and resolve through this ledger. |
| `missing_evidence` | 87 | The exact target is absent from Git and the local backend. | Preserve the gap as `missing://JointBuildGS/...`; do not guess a replacement. |

The 87 missing references comprise 42 per-building files from
`stage3_typed_readout/P1_4a_gt_sanity`, 42 per-building files from
`stage3_v4_validation/polyfit_input_audit`, and three directories from
`stage3_polyfit_phase2`.  Same-named outputs from another experiment are not
equivalent evidence and must not be linked.

The 23 historical sources are frozen evidence: seven archive references and
sixteen P0 evidence embeds.  Their old link text is part of the preserved source
record; the sidecar supplies the current semantic target without rewriting it.

## Machine contract

Rows are keyed by `(source_path, relation, raw_target)`.  Line numbers are audit
evidence, not the identity key, because navigation-only edits can move a line.
The inventory maps reviewed rows to one of these lineage states:

- repository target: `target_exists=yes`;
- external target: `target_exists=external` and `artifact://JointBuildGS/...`;
- known missing target: `target_exists=missing` and `missing://JointBuildGS/...`;
- no exact ledger row: `target_exists=no`, which fails the Work readiness gate.

The local backend has no durable-backup claim.  External-reference verification
therefore establishes present local resolution, not off-machine preservation.
