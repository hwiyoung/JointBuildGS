# Boundary map v2 measurement summary (2026-07-18)

## Population checks

| check | count |
|---|---:|
| raw_lidar rows | 199 |
| raw_lidar assembled=true | 178 |
| raw_lidar assembled=false | 21 |
| dense success in canonical population | 114 |
| dense failure in canonical population | 64 |
| 2026-07-16 C symmetric difference | 42 (21 removed + 21 added) |
| reused measurements | 164 |
| newly prepared outline/crop-pair rows | 14 |

## Assignment counts

| assignment | count |
|---|---:|
| `well_textured` | 43 |
| `textureless_correspondence_anchored` | 68 |
| `outline_only` | 30 |
| `unobservable` | 0 |
| `indeterminate_small` | 37 |

## Manual validation and dense cross-tabulation

- validation status: complete
- validation assignments available/requested: 22/22
- validation records used for accuracy: 22
- rule exact records: 15
- rule accuracy: 0.681818
- constant `well_textured` exact records: 17
- constant accuracy: 0.772727
- validation accuracy gain: -0.090909
- FM threshold status: calibrated_complete
- FM count threshold: 1146
- final calibration exact records after FM channel: 21/22
- incomplete calibration FM buildings: 0

FM pair status policy: all selected pairs processed plus at least one successful nondegenerate pair is `complete`; a successful eligible pair with pooled footprint count 0 remains complete/count0; baseline<=0.06 m pairs are excluded; pair exceptions or deadline-pending pairs make the building incomplete; incomplete FM counts are not used as negative evidence and those validation records are excluded.

| dense outcome | recorded group | count |
|---|---|---:|
| dense_failure | not_well_textured | 27 |
| dense_failure | well_textured | 37 |
| dense_success | not_well_textured | 100 |
| dense_success | well_textured | 14 |

All rows record `learning_runs_started=0`. New inference fields are limited to R1-2 crop-pair measurement and R1-4 fixed-pose FM retriangulation. FM z is DHHN orthometric after the configured 45.7 m geoid subtraction. LoD2 height is used for projection/classification only.
