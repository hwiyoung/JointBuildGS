# Boundary map v3 measurement summary (2026-07-19)

## Population and label inventory

| measurement | count |
|---|---:|
| canonical raw_lidar assembled=true | 178 |
| canonical dense assembled=true | 114 |
| canonical dense assembled=false | 64 |
| manual labels | 44 |
| manual ∩ dense-success | 0 |
| calibration labels | 79 |
| validation labels | 79 |

The manual 22/22 membership is the v2 set at seed 20260718. Dense-success labels use seed 20260719 and a 57/57 split.

## Final map assignment counts

| assignment | count |
|---|---:|
| `well_textured` | 136 |
| `textureless_correspondence_anchored` | 2 |
| `outline_only` | 3 |
| `unobservable` | 0 |
| `indeterminate_small` | 37 |
| conditional generation targets | 5 |

## Primary rule validation (pre-FM, pre-override, pre-small)

| measurement | value |
|---|---:|
| validation records | 79 |
| exact records | 72 |
| accuracy | 0.911392405 |
| constant well_textured exact records | 74 |
| constant accuracy | 0.936708861 |
| accuracy gain | -0.025316456 |
| rule_status | `failed_gain` |

| expected tier | support | predicted support | recall | precision |
|---|---:|---:|---:|---:|
| `well_textured` | 74 | 77 | 0.972972973 | 0.935064935 |
| `textureless_correspondence_anchored` | 2 | 0 | 0.000000000 | NA |
| `outline_only` | 3 | 2 | 0.000000000 | 0.000000000 |

## FM dense-dial count threshold

- measurement status: partial
- incomplete buildings: 1
- threshold status: selected_on_partial_calibration_support
- selected footprint-inside count threshold: 1
- calibration candidate total: 3
- completed calibration candidate support: 2
- incomplete calibration candidate support: 1
- actual textureless support in calibration candidates: 2
- candidates at or above threshold: 2
- candidates below threshold: 0

The threshold candidate set contains 1, every observed positive calibration-candidate count, and each observed count plus one. Selection maximizes calibration79 exact agreement; ties use the smallest integer threshold.

Incomplete FM candidates retain their primary assignment; the fixed override is then applied after the small-area rule.

Incomplete building identifiers:

- `DEBY_LOD2_4908169`

## Dense outcome cross-tabulations

### primary_rule_vs_dense_success

| dense outcome | recorded group | count |
|---|---|---:|
| dense_success | well_textured | 112 |
| dense_success | not_well_textured | 2 |
| dense_failure | well_textured | 63 |
| dense_failure | not_well_textured | 1 |

### final_map_vs_dense_success

| dense outcome | recorded group | count |
|---|---|---:|
| dense_success | well_textured | 93 |
| dense_success | not_well_textured | 21 |
| dense_failure | well_textured | 43 |
| dense_failure | not_well_textured | 21 |

## Fixed override records (full identifiers)

| building_id | primary | formula | size rule | override | final map | dense inside count | dense inside z median (m) |
|---|---|---|---|---|---|---:|---:|
| `DEBY_LOD2_4907199` | `well_textured` | `textureless_correspondence_anchored` | `textureless_correspondence_anchored` | `textureless_correspondence_anchored` | `textureless_correspondence_anchored` | 373 | -34.347425 |
| `DEBY_LOD2_8568391` | `well_textured` | `textureless_correspondence_anchored` | `textureless_correspondence_anchored` | `textureless_correspondence_anchored` | `textureless_correspondence_anchored` | 456 | -40.667009 |

Override evidence for both rows: `B-1_measured_flat_seed(FM 앵커 373·456점·W_밤샘3과제_검수_20260717 §3-1)`.

All output rows record `learning_runs_started=0`. New inference is limited to the R1′-3 FM dense-dial reciprocal-matching queue. The v2 sparse FM fields are retained as reference columns only. LoD2 remains projection/classification-only.
