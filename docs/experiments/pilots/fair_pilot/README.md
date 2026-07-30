# Fair pilot — Vaihingen Area 3 positive-control preparation

This experiment family is independent from `phases/p0-audit/` and the GS-JSO runtime.
It reuses the verified immutable Vaihingen archive read-only and stages only a
bounded Area 3 subset. GS training is out of scope and was not run.

Reproduce in order from the repository root:

```bash
scripts/experiments/fair_pilot/run_01_inventory.sh
scripts/experiments/fair_pilot/run_02_stage_area3.sh
scripts/experiments/fair_pilot/run_03_prepare_area3.sh
scripts/experiments/fair_pilot/run_04_colmap_mvs.sh
scripts/experiments/fair_pilot/run_05_stats_candidates.sh
```

Every wrapper uses Docker with host UID/GID mapping and the image IDs locked in
`configs/fair_pilot/vaihingen_area3.json`. The COLMAP wrapper exposes host GPU 1 as container
GPU 0. Whole-stage time bounds and thresholds are locked in the same config;
incremental logs and full payload remain in the external artifact workspace.
The promoted compact run record is in
`phases/fair-pilot/runs/20260714_vaihingen_area3/`.

The default external workspace is the sibling directory
`../JointBuildGS-artifacts/fair-pilot`; set `JBGS_ARTIFACT_ROOT` to override it.

The distributed ISPRS 9 cm Match-T DSM is retained as the complete MVS baseline.
The additional provided-pose COLMAP pilot is separately labeled `partial` when
both geometric and photometric fusion yield zero points.
