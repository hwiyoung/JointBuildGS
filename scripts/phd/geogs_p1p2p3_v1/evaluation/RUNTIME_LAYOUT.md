# Explicit runtime layout provenance

The `--runtime-layout /task/contracts/runtime_layout_allocator_v2.json`
argument is accepted by `seal_candidates.py`, `run_evaluation.py`, `summarize.py`,
and `case_figures.py`. The shell driver accepts it after its existing region,
stage and GPU arguments:

```bash
bash scripts/phd/geogs_p1p2p3_v1/evaluation/run_evaluation.sh P1 geometry 0 \
  --runtime-layout /task/contracts/runtime_layout_allocator_v2.json \
  --repeat-contract /task/contracts/supplemental_repeat_v1.json \
  --resource-contract /task/contracts/extraction_resource_v3.json
```

All three explicit contracts are required for the current task, after the full
21-run candidate seal. A layout-only command is an obsolete example for this
task and is rejected when the repeat/resource contracts are present. The current
automatic finalizer already passes all three arguments.

For historical tasks without these contracts, layout omission means the original
`runs/` layout; a seal produced with an explicit revision cannot be consumed by
omitting its contract. The contract SHA is bound
through candidate seal, per-region metrics/receipts, summary, selected cases and
viewer/case outputs. Its scientific configuration SHA must match the unchanged
execution contract. Paths may not escape the task.

Allocator v2 sends all final candidates to `runs_allocator_v2/`. P1 uses the
exact original completed/protected iteration8000 checkpoint, including its SHA;
P2/P3 use their new native complete8000 checkpoints. A failed source run after
the completed anchor remains explicitly failed. Auxiliary anchor extraction
must copy the declared exact complete-state PLY. Restoration receipts bind each
resumed final to that same checkpoint.

The seal includes all primary and auxiliary renderer logs, invocation/receipt
files, actual PLY/cfg_args inputs, parser snapshots and complete-state metadata.
Logged bounded TSDF depth truncation, voxel size and SDF truncation must be
finite/positive, follow the official camera-derived algebra exactly, and agree
across arms and anchor within each region/resolution. Depth truncation must also
agree across mesh-resolution sensitivity runs. Source-default depth ratio is
not mislabeled as a logged realized value.

Resources report raw per-phase wall times separately from comparable refinement
or full-pipeline cost. P1 native begins at8000; P2/P3 native begins at0. The exact
8000 trace elapsed value is an instrumented prefix ending **before** checkpoint
serialization. It is not a complete standalone anchor wall time. The original
P1 failed whole training receipt includes failed refinement and is separately
labeled `FAILED_ATTEMPT_NOT_ANCHOR_COST`; it is not added to final arm cost.
Unavailable comparable/full-pipeline values remain null.

Docker regression on 2026-09-08:54 tests passed in13.735s, including11 runtime
layout/extraction tests,13 summary tests,9 evaluation-driver tests,9 case tests,
and12 render-quality tests. Runtime image:
`jointbuildgs:geogs-official-db40c95-compat-v1`; network disabled, no GPU or
regional/reference payload mount, CPU2 and memory6GiB. The optical parity tests
used only the official source and read-only pretrained weight cache. No regional
performance was computed by these fixtures. `scientific_verdict: null`.

The later preregistered native repetition uses a second explicit argument,
`--repeat-contract /task/contracts/supplemental_repeat_v1.json`. All four Python
drivers and the shell wrapper accept both flags together. If this contract is
present in the task, omission is rejected. All three repetitions must be sealed
before any reference evaluation; a partial repetition set cannot pass the gate.

Supplemental output roots are `native_repeat_allocator_v2/<region>/D005_Pnative`.
Scientific controls and executed condition remain native. Separate evaluation
candidate IDs are `native_repeat_1.final.raw`, `.final.post`, `.anchor.raw/post`
and the declared extraction sensitivity variants. The same geometry/optical
estimators run on these candidates. `supplemental_only` distinguishes them from
the unchanged six-condition matrix, and the repeat contract SHA accompanies
all downstream evaluation/summary/case metadata. The repeated anchor remains
the identical primary complete8000 checkpoint, including primary gate hash and
actual validator/contract snapshot hashes in every phase and auxiliary variant.

Supplemental integration regression:35 tests passed in3.592s, covering six new
repetition tests plus the runtime/extraction, evaluation-driver and case tests.
A separate Docker check loaded the actual configuration/layout/repeat contracts
without regional payloads and confirmed repeat contract SHA
`3c62494f13de96dba33b1c36cbadf58e555305fee01ce641dd41f560bdfacafc`.
Repetition variation is supplementary descriptive evidence. It does not select
a preferred replicate, change primary rankings, or estimate a general noise bound.
