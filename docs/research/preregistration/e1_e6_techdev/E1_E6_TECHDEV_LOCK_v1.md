# E1–E6 non-confirmatory technical-development lock v1

- Decision: `DEC-P1-021`
- Canon: `E1E6_CANON_v1`
- Status: `USER_APPROVED / NON_CONFIRMATORY_TECHNICAL_DEVELOPMENT`
- Scientific verdict: `null`

## Frozen conditions

1. `E1_LIDAR_ROOFER`: current UAS LiDAR direct Roofer baseline.
2. `E2_MVS_ROOFER`: exact common-base MVS direct Roofer baseline.
3. `E3_GS_IMAGE`: no-external-prior gsplat 2DGS.
4. `E4_GS_ALS_UNWEIGHTED`: E3 base plus Existing ALS seed/depth/planar-normal,
   with valid-prior weight fixed to one.
5. `E5_GS_ALS_WB`: byte-identical E4 arm with the sole additional operation
   `prior_pixel_weight *= w_b`.
6. `E6_GS_LOD2_PLANES_DIAGNOSTIC`: E3 base plus Existing LoD2 wall/roof plane
   supervision; `REFERENCE_DERIVED_DIAGNOSTIC_ONLY`.

E3–E6 share image membership, train/eval split, MVS evidence, seed policy,
photometric/regularization terms, random seed, optimizer, densification, 30k
iterations, TSDF and Roofer parameters. The E5 7k lambda grid selects the common
ALS depth weight from `{0.2, 0.5, 1.0}`; the selected value is then used by both
E4 and E5. Normal weight remains `0.1`.

## Leakage and evaluation

- Evaluation scan paths are denied to every training/preprocessing routine except
  `06_semantic_gt` and `07_eval`.
- `R_shared` GroundSurface XY/stable ID is a common Stage-3 control and may rasterize
  `w_b`; its Z and roof surfaces are forbidden in E1–E5.
- E6 may read LoD2 planes but may not be evaluated against that LoD2.
- The lambda-selection/evaluation view set is development-contaminated and all
  results are non-confirmatory.
- Raw and canonical assets are immutable. Synthetic outdating is written only to a
  new derived namespace and never changes `R_shared`.

## Start and stop gates

Training starts only after exact input hashes, CRS/datum, split, sigma0, `w_b`, seed,
per-view supervision coverage, finite non-zero loss gradients and GPU memory pass.
NaN, OOM, zero-gradient, missing-cache, hash drift or E4/E5 config drift stops only
the affected stage and writes a failure receipt. Missingness is never filtered.
