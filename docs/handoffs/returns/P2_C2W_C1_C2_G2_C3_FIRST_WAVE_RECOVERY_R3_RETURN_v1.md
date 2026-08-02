# Experiment-to-Work Return — C1/C2 G2 + C3 first-wave recovery R3 v1

- handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R3-v1`
- task_id: `P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R3-v1`
- proposed_status: `BLOCKED_FOR_BOUNDED_SOURCE_CORRECTION`
- experiment_commit: `2a1aff0de049bbd9d080cea448da22e563a1002b`
- Return / 200-blocked commit: `SELF`
- scientific_verdict: `null`

## Result

The zero-scientific-payload val3dity preflight passed on its single invocation. All
six real G2 units then completed as `VALIDATION_COMPLETED_EXIT_0_VALID`; the add-once
six-unit receipt has recorded SHA-256
`35cf75466e9e52d713b6888cdc538b9817a81cf1af69284d8a695272a21006fe`.

The current-MVS adapter also passed and preserved all 222,044 points. Its add-once
output SHA-256 is
`fe754af74c9795b2ea5232a20cf46e373f70666f3e5094899489e78d1f762547`.
The C1/C2 evaluator stopped because it parsed the CityJSONSeq metadata header, whose
`vertices` array is empty, as a feature. Therefore no C1/C2 development diagnostics
or new 199-to-72 explanation completed. The frozen 127 outside the independent
quantitative set remain unscored buildings, not failed buildings.

The semantic membership manifest passed for the exact 937 members and has recorded
SHA-256
`98054b7c3185bc65cf87b59443bad63a9606fb080cddfc4a25e90dc38c5e9adc`.
The first incorrect producer-lock invocation stopped before any scientific read. The
corrected invocation read only the first RGB and first depth once, then stopped before
inference because an erroneous equal-shape precheck rejected the native 1400x1013 RGB
and 1024x741 COLMAP depth dimensions.

No semantic inference or C3 optimizer update started, so no 5k/10k/20k/30k
checkpoint exists. G2, the MVS adapter, the evaluator, Roofer and semantic execution
were not retried. C1/C2 reconstruction and Roofer were not rerun; validation,
held-out, C4, C5, Fusion W1 and `R_ext` stayed unopened. All existing R3 external
artifacts remain preserved in place.

## Exact next bounded source correction

Return exclusive writer ownership to Work Host. The next source-only correction must
skip the CityJSONSeq metadata header when selecting evaluator features and permit
native COLMAP depth dimensions while documenting the deterministic training-time
depth resize. Do not alter cohorts, scientific roles, thresholds, losses, schedule,
seed or access barriers, and do not change source in this Experiment Host turn.
