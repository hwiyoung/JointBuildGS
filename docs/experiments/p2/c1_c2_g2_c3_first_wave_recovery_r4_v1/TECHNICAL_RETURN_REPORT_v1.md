# P2 C1/C2 G2 + C3 first-wave R4 technical return

- task: `P2-C1-C2-G2-C3-FIRST-WAVE-RECOVERY-R4-v1`
- execution host: Experiment Host
- offered commit: `07f59e023aaea603788d4f5204777d3429dbcb17`
- source commit: `b519633b4cce76088fa4ea7530ecd85470c01ba4`
- accepted commit: `1eefefa3a199ae86411b8c4074ca6c93df37f871`
- technical state: `BLOCKED_PROTECTED_SOURCE_AFTER_TRAINING_COMPLETED`
- scientific verdict: `null`

## Completed once

The two corrected zero-scientific preflights passed 37 tests. The real C1/C2
evaluator then ran once against the exact development 51 and emitted 102 rows. It
reused the closed R3 six-unit G2 receipt and did not invoke val3dity,
reconstruction, Roofer, or the MVS adapter. C1 has G0/G1 `51/51`; C2 has G0/G1
`50/51`. C2 has 50 technical G2-valid rows and one unavailable row. C1 G2 remains
`null` because it is the self-reference upper baseline. G3, G4, and `PASS_usable`
remain `null` for both conditions.

All 937 exact-member semantic inferences ran offline on GPU 0. RGB and masks stayed
at native `1400x1013`; COLMAP depth stayed at native `1024x741`. Training alignment
is recorded as the existing float-depth resize to RGB shape with
`cv2.INTER_LINEAR`; neither RGB nor mask was resized. The run used fresh R4 work and
output directories and the exact R3 membership read-only.

The C3 start gate passed with 371,808 SfM points plus the closed 222,044-point MVS
seed, totaling 593,852 initial Gaussians. Seed-0 training completed exactly 30,000
updates with the frozen config. The required 5k, 10k, 20k and exact final 30k
artifacts are sealed. `final.pt` records 406,337 primitives, 812 Stage-2 groups and
319,698 grouped primitives. The trainer printed its normal `[done] 30000 iter`
completion line. The container's shell exit code 1 is isolated to an in-container
`tee` that could not initially open the host log bind under `set -o pipefail`; it is
not a Python, CUDA, OOM, optimizer, grouping, or checkpoint failure.

## Population boundary: 199 to 72

`U_target=199` is the outcome-free target roster. Only 72 buildings belong to the
independent quantitative set, arranged in nine independent groups and frozen as
51/11/10 buildings across 5/2/2 development/validation/held-out groups. R4 opened
only development 51. The 127 outside the independent set are unscored by design;
they are not failed buildings and do not enter denominators. Validation 11 and
held-out 10 remained unopened.

The previously promoted C1/C2 fixed-view panels remain the qualitative reference
without payload reread:
[`C1_C2_QUALITATIVE_EVALUATOR_SUPPLEMENT_v1.md`](../c1_c2_qualitative_evaluator_backfill_v1/C1_C2_QUALITATIVE_EVALUATOR_SUPPLEMENT_v1.md).
R4 did not relabel or recompute those panels.

## Protected-source stop for C3 development evaluation

The checkpoint is complete, but the repository does not contain an authorized real
C3 development-51 Stage-3 evaluation path:

- the activated parent first-wave packet says the footprint-free Stage-3
  C1/C2/C3 comparison is the next separately bounded task after checkpoint sealing;
- `configs/stage3/gate_s0_integrated_v1/common_interface_v1.json` declares
  `SYNTHETIC_INTERFACE_SMOKE_ONLY` and performance authority `NONE`;
- the common interface implementation states that it is not the final P2 adapter or
  a scientific-quality selection;
- the canonical decision log leaves the final P2 Stage-3 adapter, G3/G4 numerical
  thresholds and `PASS_usable` criterion pending;
- the frozen whole-scene C3 run assigns all exact 937 views to training and zero to
  evaluation, and no frozen surface extraction, development-building association,
  real Roofer configuration, or C3 qualitative protocol exists.

Running a development-51 comparison would therefore require inventing or changing
protected source/config/cohort/threshold decisions. R4 preserves the completed
checkpoint and records this as `BLOCKED_PROTECTED_SOURCE`; it does not count 51 C3
failures or fabricate stage/final/qualitative outcomes. The exact source gate is in
`control/c3_development_evaluation_source_gate_v1.json` in the R4 external namespace.

## Scope accounting

- real C1/C2 evaluator runs: `1`
- semantic inference completions: `937/937`
- C3 optimizer runs: `1`; completed updates: `30000`
- C3 Stage-3 evaluation runs: `0`
- R4 val3dity / reconstruction / Roofer / MVS-adapter invocations: `0/0/0/0`
- validation11 / heldout10 / C4 / C5 / Fusion W1 / R_ext / external-prior reads:
  `0/0/0/0/0/0/0`
- scientific verdict: `null`

The compact tables are
[`stage_counts_v1.csv`](stage_counts_v1.csv),
[`population_scope_v1.csv`](population_scope_v1.csv), and
[`qualitative_status_v1.csv`](qualitative_status_v1.csv). Exact external identities
are bound by
[`technical_result_manifest_v1.json`](../../../../artifacts/manifests/p2/c1_c2_g2_c3_first_wave_recovery_r4_v1/technical_result_manifest_v1.json).
