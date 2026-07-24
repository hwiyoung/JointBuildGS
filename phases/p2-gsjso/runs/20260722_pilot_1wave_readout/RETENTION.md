# P1W retention

The completed first-wave runtime was compacted on 2026-07-24 after all ten
20k runs and the final readout had completed. The policy preserves the
no-retraining recovery path for the current zero-roof/containment diagnosis.

## Result

- Source runtime before: 108,602,041,813 file bytes (101.14 GiB).
- Removed: 80,986,650,556 bytes (75.42 GiB).
- Source runtime retained: 27,615,391,257 file bytes (25.72 GiB).
- No Git-tracked source artifact was selected for deletion.
- Unrelated untracked documents were not touched.

The sealed figures and per-path disposition are in
`retention/retention_receipt.json` and `retention/retention_plan.json`.

## Retained

Local recovery payloads under the 20260721 run:

- ten canonical `step_020000.pt` full-state checkpoints and SHA sidecars
  (12.27 GiB);
- ten successful `scene_geometry.npz` files and extraction provenance
  (13.39 GiB);
- the materialized sparse camera model required by checkpoint readout;
- tracked pilot locks, resolved configs, calibration, canonical masks, loss
  audits, issue history, and aggregate recovery evidence.

Compact versioned evidence under this readout:

- all final scores, summaries, gates, binding audits, loss shares, and locks;
- ten assembled CityJSON predictions;
- one 20k qualitative preview per run;
- full-state, extraction, classification, and Roofer receipts per run;
- compact JSON receipts from the superseded training/postprocess attempts;
- SHA mapping from each compact copy to its original runtime path.

## Removed

- 5k, 10k, and 15k checkpoints and their sidecars;
- unreferenced model-only `final.pt` files;
- raw and classified LAS files that can be regenerated from the retained NPZ;
- failed training runtime and the first three failed postprocess attempts,
  after copying their compact JSON receipts;
- intermediate renders and TensorBoard event files, after retaining one final
  preview per run;
- materialized RGB, MVS maps, mono normals, dense seed, and superseded mask
  attempts whose upstream sources and pinned preparation assets were verified.

## Recovery boundary

- Reading the result and reviewing the report: immediate from this directory
  and `../20260724_pilot_1wave_report/`.
- Independent datum re-score: use the ten
  `prediction_pack/*/assembled.city.json` files.
- Classifier/Roofer rerun without training: regenerate LAS from the retained
  geometry NPZ files. The original pure classifier workload was about nine
  minutes for all ten runs.
- Geometry re-extraction is not required while the NPZ cache is retained. The
  original ten-run extraction took 11.157 hours.
- Training resume is not retained as an immediate operation. The locked
  materialized inputs must first be rebuilt from the verified upstream data,
  and extending beyond 20k requires a separately reviewed checkpoint/config
  migration.

Historical manifests still record the original LAS and materialized-input
paths. A strict path-existence validator will therefore require regeneration
of those payloads before it can pass. Their recorded hashes and the compaction
disposition remain preserved in the retention plan and receipt.

After the zero-roof/containment diagnosis is closed, the ten geometry NPZ cache
files can be reviewed for a second-stage deletion that would release another
13.39 GiB. They are intentionally retained for now to avoid repeating the
11-hour extraction.

## Verification note

The cleanup script compiled in the pinned training image. The first datum
re-score check was intentionally stopped when that image reported its expected
absence of `laspy`; no output was changed. The same read-only check was then
run in the pinned P0/scoring image used by the first-wave scoring chain. Both
recomputed datum-audit CSV files were byte-identical to the published files.
The machine-readable details are in `retention/retention_verification.json`.
