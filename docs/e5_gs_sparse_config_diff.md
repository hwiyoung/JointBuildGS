# E5 GS-Sparse Config Diff (A3)

- CRS: EPSG:25832
- Branch: `feat/p2-structure-learn`
- HEAD before A3 commit: `2ebd8afbdce075317fc7ae2cfe23be8661589931`
- Phase run: `phases/p2-gsjso/runs/e5p_sparse_config_20260706_000204/versions.txt`
- Recipe string: `GS(D4; seed-protect; pho1·sem0.1·nc0.05·dep0.03·nrm-off·str1[g2;na0.08;cp0.01;warm15k]; gssem)`
- Sparse seed: `results/tum_transfer/mob_analysis/seed/seed_sparse.ply` (369225 points)
- Sparse seed source: `phases/p0-audit/data/work/mvs/openmvs/colmap_txt/sparse/points3D.txt`

## Scalar Key Diff

| key | D4 dense | E5 sparse | classification |
|---|---|---|---|
| `init_pointcloud` | `/workspace/JointBuildGS/results/tum_transfer/mob_analysis/seed/seed_dense.ply` | `/workspace/JointBuildGS/results/tum_transfer/mob_analysis/seed/seed_sparse.ply` | seed |
| `out_dir` | `/workspace/JointBuildGS/results/tum_transfer/mob/gs_d4_dense` | `/workspace/JointBuildGS/results/tum_transfer/mob/gs_d4_sparse` | bookkeeping |

## Recipe Equality Check

- Recipe scalar diffs excluding seed path and output directory: 0
- Result: 0 recipe-term differences. `out_dir` differs only to prevent overwriting dense outputs.

## Unified Diff

```diff
--- configs/tum_mob/gs_d4_dense.yaml
+++ configs/tum_mob/gs_d4_sparse.yaml
@@ -1,21 +1,13 @@
-# P2-D4 (CORRECTED) — minimal "normalize cp only" re-train (flatten GS roof curvature).
-# Base = gs_prior_full_dense.yaml (reported D). CORRECTION (2026-06-25, 김휘영): the earlier D4 OVER-APPLIED
-# per-term normalization (photo 5.6 / nc 2.1 / sem 0.92) -> early photo/psnr lag. Corrected D4 keeps D's
-# HEALTHY terms (photo 1.0, nc 0.05, sem 0.1, na 0.08) and surgically fixes only the 3 problem terms:
-#   cp     : effective 0.08 -> 0.01  (de-dominate; cp share 68% -> ~31%, to photo parity)
-#   depth  : 0.1 -> 0.03             (de-noise: CV 1.74 noisy MVS target -> lower pin)
-#   normal : 0.15 -> 0               (remove noisy external MVS normal)
-# Engine UNCHANGED (config-only). NOT a goalpost-moving variant — a config-error correction; re-locked as D4.
-# Effective scalar = weight that multiplies the RAW loss in train.py loss_total
-#   (cp = w_structure*w_structure_cp ; na = w_structure*w_structure_na ; others = their w_).
-# Predicted weighted shares (D-run means): cp 31% / photo 31% / sem 19% / depth 17% / nc 2% / normal 0
-#   -> no term > 40% (vs reported D cp 68%). See docs/W_D4_precheck.md / P2_D4_사양서_사전등록_20260625.md §2.
+# P2-D4 (CORRECTED) — sparse seed arm for E5 preregistration.
+# Derived from gs_d4_dense.yaml. Recipe terms are identical; init seed is the
+# native COLMAP sparse points3D cloud. out_dir is separated only to avoid
+# overwriting dense outputs.
 seed: 0
 device: cuda
 
 data_root: /workspace/JointBuildGS/results/tum_transfer/data_geoidfix   # MUST-EQ
 
-init_pointcloud: /workspace/JointBuildGS/results/tum_transfer/mob_analysis/seed/seed_dense.ply   # MUST-EQ
+init_pointcloud: /workspace/JointBuildGS/results/tum_transfer/mob_analysis/seed/seed_sparse.ply   # MUST-EQ
 init_pointcloud_mode: concat
 seed_protect: true                                                       # MUST-EQ
 seed_log_footprints: /workspace/JointBuildGS/results/tum_transfer/analysis/footprints_aoi.geojson
@@ -97,4 +89,4 @@
 max_iter: 30000                 # MUST-EQ
 eval_every: 2000
 ckpt_every: 10000
-out_dir: /workspace/JointBuildGS/results/tum_transfer/mob/gs_d4_dense
+out_dir: /workspace/JointBuildGS/results/tum_transfer/mob/gs_d4_sparse
```
