# Experiment-to-Work Return — C1/C2 G2 + C3 first-wave recovery R2 v1

- handoff_id: `P2-W2C-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R2-v1`
- task_id: `P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R2-v1`
- proposed_status: `BLOCKED_FOR_PINNED_CLI_TOKENIZATION_FIX`
- experiment_commit: `3acec2658b77c13a3819bc5d9a5721ffb6beacae`
- scientific_verdict: `null`

## Result

The first G2 process stopped before geometry validation. The pinned val3dity 2.6.0
CLI rejects `--option=value`; the frozen command must pass option and value as two
tokens. A zero-scientific-payload synthetic stdin check confirmed that the corrected
tokenization emits the exact header/feature stream already supported by the parser.

Only the first C2 unit was read and hashed once in R2 before the CLI rejection. No
completed validation result was produced, the other five C2 units were not read, and
MVS adapter, semantic inference and C3 optimization remained at zero. C1/C2
reconstruction and Roofer were not rerun; validation and held-out stayed unopened.

## Exact next action

Return writer ownership, change only the four val3dity option tokens in the candidate
config, preserve raw stdout/stderr add-once before parsing, and require an actual
pinned-container synthetic stdin preflight before any real C2 read. Do not retry a
real C2 unit before that preflight passes.
