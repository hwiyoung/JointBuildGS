# P1-4a val3dity Enablement And Rerun

## 1. Purpose

Previous status was `BLOCKED_VAL3DITY_MISSING`. This rerun searches for or builds `val3dity`, then validates the existing `relation_readout.city.json` artifacts only. No CityJSON regeneration or relation read-out code change was performed.

## 2. val3dity Installation/Search Result

- Found path: `NONE`
- Path recovery search: `results/stage3_typed_readout/P1_4a_gt_sanity/val3dity_enable/path_recovery_search.json`
- Search JSON: `results/stage3_typed_readout/P1_4a_gt_sanity/val3dity_enable/val3dity_search.json`
- Build report: `results/stage3_typed_readout/P1_4a_gt_sanity/val3dity_enable/build_report.md`
- Build status: `BLOCKED_DEPENDENCY`

Build did not produce a runnable validator. Configure/build logs are preserved:
- `results/stage3_typed_readout/P1_4a_gt_sanity/val3dity_enable/build_configure.log`
- `results/stage3_typed_readout/P1_4a_gt_sanity/val3dity_enable/build_compile.log`

Recommended dependency install note, not executed automatically:
```bash
sudo apt-get update
sudo apt-get install -y cmake g++ git libcgal-dev libeigen3-dev libgeos++-dev libboost-filesystem-dev libboost-system-dev
```

Path recovery result:
- Executable paths found by requested broad search: none
- `grep -R "val3dity" -n scripts src results | head -200` matched 200 lines; scripts call `val3dity` by command name, but no local executable path was recovered.

## 3. Schema Validation

| bid | schema_status | notes |
| --- | --- | --- |
| B1 | SKIPPED_VAL3DITY_ENABLE_BLOCKED | schema validation skipped because val3dity enablement stopped at source build/dependency phase |
| B2 | SKIPPED_VAL3DITY_ENABLE_BLOCKED | schema validation skipped because val3dity enablement stopped at source build/dependency phase |
| B8 | SKIPPED_VAL3DITY_ENABLE_BLOCKED | schema validation skipped because val3dity enablement stopped at source build/dependency phase |
| B6 | SKIPPED_VAL3DITY_ENABLE_BLOCKED | schema validation skipped because val3dity enablement stopped at source build/dependency phase |
| B0 | SKIPPED_VAL3DITY_ENABLE_BLOCKED | schema validation skipped because val3dity enablement stopped at source build/dependency phase |
| B3 | SKIPPED_VAL3DITY_ENABLE_BLOCKED | schema validation skipped because val3dity enablement stopped at source build/dependency phase |

## 4. val3dity Formal Validity

| bid | val3dity | errors | returncode | report_path |
| --- | --- | --- | --- | --- |
| B1 | BLOCKED_DEPENDENCY | BLOCKED_DEPENDENCY | NA | NA |
| B2 | BLOCKED_DEPENDENCY | BLOCKED_DEPENDENCY | NA | NA |
| B8 | BLOCKED_DEPENDENCY | BLOCKED_DEPENDENCY | NA | NA |
| B6 | BLOCKED_DEPENDENCY | BLOCKED_DEPENDENCY | NA | NA |
| B0 | BLOCKED_DEPENDENCY | BLOCKED_DEPENDENCY | NA | NA |
| B3 | BLOCKED_DEPENDENCY | BLOCKED_DEPENDENCY | NA | NA |

## 5. Geometry Metrics Kept

| bid | h_err | recall | precision | F_score | vol_ratio | footprint_IoU | Hausdorff | Chamfer |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 0.0000 | 0.990 | 0.990 | 0.990 | 1.000 | 1.000 | 0.7375 | 0.2113 |
| B2 | 0.0000 | 1.000 | 0.999 | 0.999 | 1.620 | 0.997 | 0.6752 | 0.1671 |
| B8 | 0.0010 | 0.988 | 0.994 | 0.991 | 1.392 | 0.997 | 0.6726 | 0.1854 |
| B6 | 3.6070 | 0.883 | 0.931 | 0.907 | 0.630 | 0.992 | 3.9262 | 0.2859 |
| B0 | 0.0000 | 0.902 | 0.906 | 0.904 | 2.164 | 0.999 | 2.3981 | 0.2671 |
| B3 | 7.3050 | 0.365 | 0.320 | 0.341 | 0.956 | 0.970 | 11.4784 | 1.8713 |

## 6. Formal GO/NG Update

- Final decision: `E0_BLOCKED_DEPENDENCY`
- Simple/medium rule: `BLOCKED`; hits: none
- Hip branch strict rule (h_err < 2m): `BLOCKED`
- Hip branch relaxed rule (h_err < 4m): `BLOCKED`
- Complex branch: `BLOCKED`
- Warnings: none

## 7. Failure Analysis

| error_code | interpretation |
| --- | --- |
| BLOCKED_DEPENDENCY | See val3dity report for code-specific context; no extra inference added. |

No val3dity pass is inferred from visualization or from geometry-side metrics. If validation did not run, rows remain blocked rather than passing.

## 8. Next Action

- Resolve validator build/install blocker first, then rerun this validation-only script.

## Self-verification

- PASS: val3dity executable found or build failure reason written.
- BLOCKED: 6 bid x relation_readout.city.json validation attempted.
- PASS: each bid has val3dity_report.json or explicit failure reason.
- PASS: metrics_val3dity_rerun.json exists for each bid.
- PASS: summary CSV/JSON exists.
- PASS: final REPORT exists.
- PASS: old `BLOCKED_VAL3DITY_MISSING` decision replaced by `E0_BLOCKED_DEPENDENCY`.
