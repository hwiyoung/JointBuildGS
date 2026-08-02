# Codex-to-Work Return ? P2 C1/C2 finalize-only recovery R4 v1

## Return metadata

- handoff_id: `P2-W2C-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-v1`
- task_id: `P2-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-v1`
- source commit: `9a03711b3c4d4a61717ce7745741152dbc2152d4`
- activation commit: `b6514a3396698835aaeb885bbe696fc8827c37bb`
- offered commit: `c8cf119930929915248551c5e8a700ee7e0747fd`
- accepted commit: `dab3c749293ca3d7b4503eb3a778a8de266afae4`
- output commit: `SELF`
- 200 receipt: `PENDING_SEPARATE_200_VERIFIED_EVENT`
- 300 receipt: `PENDING_DIRECT_CHILD_300_CLOSED_EVENT`
- run_id: `P2-C1-C2-FEASIBILITY-PILOT-FINALIZE-RECOVERY-R4-RUN-v1`
- finalization_operation_id: `f363744429638b0709f3e5e981c5767c1c6695456e82faaa4967f1b2cfa8f886`
- completed_at: `2026-08-02T13:20:05+09:00`
- proposed technical status: `READY_FOR_WORK_HOST_REVIEW_C1_C2_DEVELOPMENT_COMPLETE`
- scientific_verdict: `null`

## Answer first

The bounded R4 finalizer completed once and produced the exact frozen 102-row C1/C2
development result surface: 51 buildings for C1 and the same 51 for C2. It did not
rerun Roofer or reconstruction. C1 produced internally screened geometry for 51/51;
C2 produced it for 50/51. The sole C2 failure is `DEBY_LOD2_4907183`, which has 14
independent-UAS score cells but no overlapping frozen MVS component.

This is a development feasibility result, not a held-out scientific verdict. C1 is a
self-reference upper baseline and cannot be treated as an independent-reference
accuracy comparator. Canonical G2, G3, G4 and `PASS_usable` remain null. The useful
C3 design signal is that C1 and C2 roof-normal errors are identical for all 50 paired
scored buildings, while their differences are dominated by component-wise vertical
offsets and four C2 coverage cases. C3 strategy should therefore prioritize stable
component association/coverage and vertical alignment, keeping roof normal/shape as
a guardrail. It should not be chosen from an apparent C1-versus-C2 rank.

## Exact result surface

| Item | C1_L_upper | C2_MVS |
|---|---:|---:|
| frozen development denominator | 51 | 51 |
| G0 generated | 51 | 50 |
| provisional internal G1 true | 51 | 50 |
| continuous-score rows | 51 | 50 |
| median independent-UAS vertical coverage | 1.000 | 1.000 |
| mean / median height MAE (m) | 6.225 / 5.216 | 4.366 / 2.995 |
| mean / median RMSZ (m) | 7.005 / 5.812 | 5.211 / 3.945 |
| mean / median surface RMSE (m) | 7.005 / 5.812 | 5.576 / 3.992 |
| mean / median normal error (deg) | 12.597 / 7.557 | 12.838 / 7.710 |

The C2 vertical-coverage mean is 0.9713 with 47/50 scored buildings at full coverage.
The four non-full cases are `DEBY_LOD2_4907177` (0.1333), `4907180` (0.5882),
`4907176` (0.8440), and `4906965` (0.9985). C2 RMSZ ranges from 0.337 to 20.029 m.
High full/near-full-coverage vertical-error diagnostics include `4959325`, `4907205`,
`4906984`, `4906983`, and `4906966`.

Across the 50 paired scored buildings, C2 RMSZ is lower for 29 and higher for 21;
the median C2-minus-C1 RMSZ difference is -0.189 m. This is descriptive only. C1 is
self-reference and the development groups are severely imbalanced (`47/1/1/1/1`).
The group-balanced descriptive C2 means are coverage 0.9938, height MAE 2.796 m,
RMSZ 3.010 m, surface RMSE 3.090 m, and median-normal error 11.921 degrees. No
inferential or population-generalizable claim is made.

## C3 design evidence from C1/C2

- The 50 paired buildings have exactly identical normal-angle metrics between C1 and
  C2. The current Stage-3 output difference therefore does not show distinguishable
  roof-orientation improvement.
- Signed-height C2-minus-C1 differences repeat by frozen C2 component: +0.688 m for
  35 buildings and -2.307 m for eight, with the remaining buildings tied to other
  components. Component-aware Z consistency is the primary first-wave diagnostic.
- Association/coverage robustness is the second target: one building has no C2
  component, and three scored buildings have materially partial coverage.
- C3 must continue to use the exact common current image/pose base and may use only
  development diagnostics for strategy formation. Independent UAS remains score-only
  after input/geometry freeze. Validation 11 and held-out 10 remain unopened.
- A C3 strategy document may define a small bounded development screening plan, but
  C3 execution requires a separately reviewed and activated DRAFT packet.

## Reuse, reproducibility and no-repeat evidence

- Exact sealed R3 derived input: 22 records / 12,920,322 bytes.
- Accepted artifact identity: `46e2da58e177d0aaaba453e316cc8a5d64a24d67b2edc1504299fe22d9ea261f`.
- Each accepted record was processed and digested in one stream once; cache reuse
  prevented reopening within finalization.
- Reused R3 operation units: 7; duplicate Roofer calculations prevented: 94.
- R4 Roofer invocations: 0.
- Original scientific source reads/rehashes: 0.
- Operation LAS reads/rehashes: 0; point counts came from bound LAS1.2/PF3 byte ledgers.
- R3 writes: 0. Metadata-only R3 inventory remained 521 regular files,
  55,170,598 bytes, zero symlinks.
- R4 output namespace: 9 regular files, 301,158 bytes, zero symlinks, no pending state.
- External result records verified: 7; promoted Git records verified: 6.
- Result schema: 102 rows validated, 0 errors, 102 unique `(building_id, method_id)`.
- Validation, held-out, C3-C5, LoD1/LoD2, Fusion W1 and `R_ext` accesses: 0.
- `scientific_verdict` remains null throughout.

The R4 namespace now exists and any wrapper rerun is fail-closed. Do not rerun R3 or
R4, do not reopen the five original inputs, and do not create another receipt for
this event.

## Promoted evidence

- `docs/experiments/p2/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/C1_C2_DEVELOPMENT_REPORT_v1.md`
- `docs/experiments/p2/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/building_method_metrics_v1.csv`
- `docs/experiments/p2/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/group_balanced_descriptive_v1.csv`
- `docs/experiments/p2/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/condition_group_technical_summary_v1.csv`
- `docs/experiments/p2/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/development_input_definition_v1.csv`
- `docs/experiments/p2/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/preselected_case_metrics_v1.csv`
- `artifacts/manifests/p2_baselines/c1_c2_feasibility_pilot_finalize_recovery_r4_v1/technical_result_manifest_v1.json`

Qualitative fixed-view evidence is explicitly `NOT_RENDERED` because no frozen camera
or renderer belongs to this bounded pilot. The five preselected case rows are
promoted as quantitative case diagnostics, not rendered visual evidence.

## Independent post-run reviews

Three mutually independent read-only reviews passed:

- scientific scope/leakage: exact development-only 51x2 surface, independent-UAS
  score-only isolation, C1 self-reference isolation, and no protected split/workstream
  access;
- two-host ownership: exact direct source?activation?offer?accepted chain, allowed-only
  Git changes, Experiment Host ownership through Return, unchanged sealed R3 metadata,
  and valid preconditions for verified/closed receipts;
- reproducibility/no-repeat: exact 22-record one-stream reuse, 102 unique rows, seven
  reused operations, 94 duplicate computations prevented, nine-file add-once R4
  namespace, six promoted records, zero Roofer/original/LAS rereads, and null verdict.

## Remaining limitations

- This is a development pilot over 51 buildings in five groups, with group sizes
  `47/1/1/1/1`; it is not a confirmatory estimate for all 199 AOI buildings.
- One C2 building lacks an associated MVS component and four scored cases are not at
  full vertical coverage.
- Canonical topology validation and final usable thresholds are not frozen here, so
  G2/G3/G4/`PASS_usable` remain null.
- No qualitative fixed-view render is available in this bounded task.
- C3, C4, C5, validation and held-out performance were not executed.

## Recommended next bounded task

After `200-verified` and direct-child `300-closed` return writer ownership, prepare one
Work-Host-only **C3 strategy DRAFT** from these development diagnostics. It should
freeze a bounded image-only GS screening strategy focused first on component-aware
vertical alignment and coverage/association robustness, preserve roof-normal/shape as
a guardrail, and keep validation/held-out closed. Do not activate or execute C3 until
that DRAFT receives separate review and authorization.

`scientific_verdict` remains `null`.
