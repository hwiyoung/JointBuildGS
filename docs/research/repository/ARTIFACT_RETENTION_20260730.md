# Local artifact retention cleanup — 2026-07-30

## Outcome

Two reviewed, fail-closed cleanup passes removed `107,048,153,265` logical
bytes (`99.70 GiB`) and `3,256` files from the sibling
`JointBuildGS-artifacts` workspace. Empty and generated layout cleanup also
removed 2,295 directory entries. Apparent workspace size changed from
`490,795,440,947` bytes (`490.80 GB`) to `383,737,875,074` bytes (`383.74 GB`),
a reduction of `107.06 GB` (`21.8%`).

The immutable plan and sealed receipt are:

- `artifacts/manifests/local_artifact_retention_plan_20260730.json`
- `artifacts/manifests/local_artifact_retention_receipt_20260730.json`
- `artifacts/manifests/local_artifact_retention_pass2_plan_20260730.json`
- `artifacts/manifests/local_artifact_retention_pass2_receipt_20260730.json`

The cleanup did not rewrite Git history, edit `.gitignore`, delete unique raw
data, delete final experiment results, or touch active Fusion payloads.

## Deleted scope

| Class | Count | Logical bytes | Deletion gate |
|---|---:|---:|---|
| MatrixCity source archives | 21 files | 73,471,507,963 | local SHA-256 equals the official Hugging Face LFS OID at pinned revision `22237509a7a16d5c0136b58b39597629a63b338d`; extracted copies and live depth/normal links remain |
| Historical intermediate checkpoints | 29 files | 5,028,520,496 | exact path is not referenced by current tracked or untracked text; every affected checkpoint directory retains its latest step and `final.pt` |
| Exact duplicate evidence, bytecode/download caches, retired placeholders | 257 files | 21,881,241 | canonical evidence SHA-256 matches; remaining content is generated or empty |
| OpenMVS densification cache and superseded serialized intermediates | 927 files | 7,011,088,110 | `scene.mvs`, final `dim_dense.ply`, DIM LAZ, and live COLMAP dense inputs remain |
| Superseded P0 diagnostic attempts and exact duplicate scratch inputs | 218 files | 302,723,329 | eight canonical diagnostic runs remain; duplicate GeoJSON SHA-256 matches the retained canonical copy |
| Regenerable P0 Roofer LAS intermediates | 1,455 files | 18,930,284,905 | compact CityJSON/metrics/log/config records and the exact NPZ regeneration inputs remain |
| Closed fair-pilot workspace and Python bytecode | 349 files | 2,282,147,221 | immutable source ZIP plus compact run manifest, metrics, log, summary, and versions remain |

The MatrixCity archives are recoverable from the pinned official dataset tree:
`https://huggingface.co/datasets/BoDai/MatrixCity/tree/22237509a7a16d5c0136b58b39597629a63b338d`.
The plan records the per-file URL, byte count, and SHA-256.

## Retained scope

- all extracted MatrixCity images, depth, normal, semantic, sparse, and point-cloud working data;
- all unique P0 raw inputs, live COLMAP/Fusion inputs, canonical P0 runs, and
  every currently referenced P0 LAS family;
- all completed Pilot 1-wave retained full-state checkpoints, geometry NPZ files, and prediction/receipt pack;
- all current Fusion W1 payloads and the existing staged, unstaged, and untracked Fusion work;
- all final checkpoints and the latest step checkpoint in every affected historical run;
- all checkpoint paths referenced by current documentation, manifests, catalogs, or run receipts;
- the nightly RV1 report and its cache, until its repo-relative source resolver is corrected;
- migration TSV/CSV/audit records, the referenced legacy source snapshot, and the unique Fusion Roofer runtime log.

## Post-cleanup verification

- planned targets remaining: `0 / 66`;
- retained latest checkpoints: `76 / 76`;
- retained MatrixCity extracted counterparts: `21 / 21`;
- retained canonical evidence files: `18 / 18`;
- MatrixCity source archives remaining: `0`;
- broken MatrixCity depth/normal links: `0`;
- active `phase-payloads/p2-gsjso/runs/fusion_w1` was outside the deletion plan.
- pass-2 planned targets remaining: `0 / 2,425`;
- pass-2 retained gates: P0 inputs `7 / 7`, canonical P0 runs `8 / 8`,
  regeneration inputs `8 / 8`, fair-pilot compact records `5 / 5`;
- pass-2 raw-data deletions: `0`; active-Fusion deletions: `0`.

The removed Roofer LAS files were payload intermediates, not the compact
scientific records. Their own `prep_metrics.csv` files intentionally remain as
historical provenance and therefore contain expired local payload paths. The
pass-2 receipt records this explicitly; regeneration requires the retained NPZ
inputs and the tracked scripts/configuration.

## Remaining storage

| Artifact root | Apparent bytes | Current role |
|---|---:|---|
| `phase-payloads/` | 172,780,832,346 | P0 data/runs plus active P2/Fusion payloads |
| `results/` | 110,662,146,773 | retained experiment results; `tum_transfer/` alone is 91.06 GB and is referenced or unique |
| `data/` | 100,121,408,169 | almost entirely the extracted MatrixCity working dataset |
| `reports/` and small control roots | 173,483,690 | compact reports, manifests, migration records, quarantine receipts, and logs |

The exact small-root total is intentionally read from the receipts rather than
treated as a stable quota. The three large roots above account for effectively
all of the remaining workspace.

There are currently 496 broken compatibility symlinks in the artifact
workspace: 483 under active `phase-payloads/p2-gsjso/runs/fusion_w1`, eight
under `results/tum_transfer`, four legacy `data` links, and one fair-pilot
staging link. They were not created or modified by either deletion plan, but
they must be repaired by the resolver/mount migration before another aggressive
compaction pass.

## Next reduction priority

The remaining `383.74 GB` is no longer dominated by obvious junk. Further
reduction should proceed only after these gates, in order:

1. repair the repo-relative resolver, Docker compatibility mounts, and the 496
   broken symlinks;
2. close Fusion W1 and create a run-specific resume/evidence retention pack;
3. define an external canonical location, checksum manifest, and tested
   rehydration procedure before removing any local raw or extracted dataset;
4. compact still-referenced P0/TUM results only after their consumers have been
   migrated to compact manifests.

Until those gates exist, deleting the remaining large roots would remove active
inputs, unique scientific evidence, or the only local working copy rather than
perform storage hygiene.
