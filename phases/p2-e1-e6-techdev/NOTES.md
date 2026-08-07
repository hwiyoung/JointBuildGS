# E1–E6 execution notes

## 2026-08-06 — canonical reset

- Historical C1–C5 IDs and artifacts remain unchanged.
- New execution IDs are E1–E6 per `DEC-P1-021`.
- Repository invariant resolves the requested official-2DGS-fork wording to the
  existing gsplat implementation.
- E6 is non-confirmatory `REFERENCE_DERIVED_DIAGNOSTIC_ONLY`.
- Root `prep/`, `runs/`, and `logs/` are replaced by the canonical external phase
  payload namespace; this file is the phase-local NOTES ledger.
- Existing evidence verifies fewer than five real construction/demolition changes;
  deterministic synthetic outdating is therefore required on derived priors only.
- `R_shared` XY/stable ID remains unchanged even when synthetic prior geometry is
  removed, inserted, or height-scaled.

## 2026-08-06 — Phase 0 inventory and prior preparation

- Canonical payload root:
  `phase-payloads/p2/e1_e6_techdev_v1/P2-E1-E6-PRIOR-FUSION-TECHDEV-v1`.
- Exact view roles: 937 visible, 820 train, 117 held out by the sorted-every-8th
  rule. The current 2024 ULS evaluation scan is path-separated and has
  `training_allowed: false` in `prep/inventory.json`.
- The first deterministic all-199 synthetic draw contained three buildings with
  no jointly valid MVS/ALS DSM cells. Those derived files were recoverably moved
  to `quarantine/unsupported_synthetic_selection/`; they are not inputs.
- Final synthetic eligibility is frozen as at least 20 jointly valid raw
  MVS/Existing-ALS DSM cells. Seed 20260806 draws 9 of the 146 eligible buildings:
  four removals, two donor insertions, and three height scalings. The selection is
  in `prep/synthetic_changes.json`; raw ALS/LoD2 and `R_shared` were not modified.
- Existing ALS preparation uses only classes 2 and 6, frozen +45.7 m vertical
  datum shift, GS-local offset `[690953, 5336071, 604]`, and 0.30 m voxelization.
  The output contains 2,240,002 points; receipt:
  `prep/existing_als_synthetic_receipt.json`.
- DSM resolution is 0.5 m on one aligned EPSG:25832 grid. Final
  `sigma0=1.1276048950195312 m`; 152 buildings have measured overlap and 47
  unsupported edge/no-overlap buildings receive the explicit conservative
  fallback `w_b=1`. Full values are in `prep/w_b.json`.
- MVS seed attempt at voxel 0.30 m yielded 4,088,100 points and was rejected by
  the 1M–3M gate. It is retained as
  `quarantine/seed_voxel030_out_of_range.ply`. The accepted 0.40 m
  (`effective training GSD 0.133333 m x 3`) seed contains 2,255,469 points;
  receipt: `prep/seed_dense.receipt.json`.
- E4/E5 use one identical ALS cache. PCA uses 20 neighbors; only curvature
  `<0.02` supplies normal supervision. Cache totals are 34,304,795 depth pixels
  and 25,814,339 planar-normal pixels across all 937 views. Base confidence is
  exactly one; E4/E5 differ only in the later `w_b` multiplication switch.
- The initial LoD sampler accidentally included unselected buildings from both
  source GML tiles; it was stopped at 38/937 views and moved to
  `quarantine/partial_unbounded_lod/`. The corrected loader sets
  `include_unselected=false` and contains exactly the shared 199 buildings.
- Corrected E6 LoD sampling has 673,792 points at 1 point/0.5 m2: 494,610 wall
  and 179,182 roof. All samples have a shared-building assignment; the 937-view
  cache contains 18,305,118 projected plane correspondences. Receipt:
  `prep/lod_prior/receipt.json`.
- Final seed unions use dense-MVS priority in a common 0.40 m duplicate voxel.
  E4/E5 share one 2,620,376-point `seed_dense_lidar.ply` (ALS downsample 0.75 m);
  E6 uses a 2,790,288-point `seed_dense_lod.ply`. The earlier 0.30 m union is
  retained only under `quarantine/seed_union_voxel030/`.
- Mandatory sanity maps exist under each E3–E6 `runs/*/sanity/` directory. The
  E5 map visibly separates low-w_b red prior support from trusted green support;
  the E6 map shows wall/roof plane-normal vectors. QA is human-visible but does
  not pause the pipeline.

## 2026-08-07 — training memory/runtime preflight

- A direct E3 smoke using all 2,255,469 dense-seed points produced 2,627,277
  initial Gaussians after the common SfM base. One iteration completed in 223 s
  and wrote a 652 MB checkpoint; this is retained under `smoke/E3` as the
  rejected full-seed execution preflight.
- Seed files remain unchanged at their required 1M–3M geometry counts. The
  runnable common adapter deterministically selects 300,000 rows with NumPy
  generator seed 0, then concats those rows to the exact common SfM base. This
  yields 671,808 initial Gaussians for every E3–E6 condition. The adapter and
  index seed are identical across conditions; E4 and E5 read the same exact
  `seed_dense_lidar.ply`, so no E4/E5 control dimension is introduced.
- `max_gaussians=800000` remains the shared cap. One-step subsampled smoke runs
  completed for E3, E4, E5, and E6 with 671,808 initial/final Gaussians and no
  prior map, loss-shape, CUDA, or backward exception. At iteration 1 the E4/E5
  total losses are identical as required by the shared 2k warmup; their only
  post-warmup difference remains the locked w_b multiplication switch.
- The final loss audit corrected two preflight gaps before any formal run:
  MVS depth now uses metric Huber with `delta=sigma0`, and both MVS depth and
  normal weights use the common 2k warmup plus 2k linear ramp. MVS normals use
  the preregistered signed dot-product form.
- ALS PCA normals are cached in camera coordinates and deterministically oriented
  toward each camera. Rendered world normals are rotated to that same camera
  frame before the signed `1-dot` E4/E5 loss. E6 rendered normals receive the
  same world-to-camera rotation before the LoD plane-angle gate; this removes the
  coordinate-frame mismatch found in the smoke implementation.
- Formal training records a 2-second GPU-memory-used trace and its peak in each
  run's `control/operation.json`; evaluation propagates this value into
  `metrics.json`.
- Rebuilding the corrected ALS cache first failed after PCA because the prior
  preflight payload was root-owned. Only this exact task payload was transferred
  to the current operator UID; the ALS step was rerun and completed 937/937.
- The first parallel final-smoke launch exposed a one-time gsplat CUDA-extension
  build race in the shared cache. E4's failed partial smoke directory is retained
  as `quarantine/smoke_E4_cuda_cache_race`; after E3 completed the cache build,
  E4 and E6 were rerun serially and both completed one forward/backward step.
- Targeted E1–E6 plus historical C4 regression tests passed 12/12. The Stage-2
  unittest discovery passed 101 tests and skipped one; two unrelated P1W pytest
  modules could not import because the pinned `jointbuildgs:dev` image does not
  contain pytest. Repository instruction validation and its 13 sync tests passed
  separately. The missing pytest dependency is recorded rather than installed on
  the host or hidden.

## 2026-08-07 — first formal lambda-grid recovery

- The first formal lambda=0.2 run reached iteration 26 after CUDA initialization
  and then stopped on a training view whose valid MVS-normal mask was empty.
  The strict signed-normal primitive correctly rejects an empty mask when called
  directly, but the per-view training adapter had not implemented the valid
  empty-sum case. The partial run and full traceback are retained; no checkpoint
  was promoted.
- Recovery keeps the strict primitive unchanged and adds an optional per-view
  adapter that returns differentiable zero with support count zero only when the
  entire mask is empty. Nonempty invalid priors still fail closed. The exact
  failed lambda step is rerun from initialization; completed outputs are not
  reused.
- The lambda-grid runner now mounts the same task-local XDG and Torch-extension
  caches as the full-condition runner. This changes no scientific configuration;
  it prevents recompiling the identical gsplat CUDA extension in each isolated
  grid container.

## 2026-08-07 — Phase 2 lambda grid complete

- All three E5 technical grid arms completed 7,000 iterations. Final held-out
  MVS-depth MAE was 7.719707 m for lambda 0.2, 11.652377 m for lambda 0.5, and
  13.670931 m for lambda 1.0.
- The locked selection rule therefore chose `lambda_L=0.2`. The result is in
  `prep/lambda_selection.json` and `prep/lambda_grid.md`. E4 and E5 materialize
  this exact same selected depth weight; their normal weight remains 0.1 and
  their only scientific difference remains the E5 `w_b` multiplication.
- Final Gaussian counts for the grid arms were 681,761 (0.2), 622,045 (0.5),
  and 626,602 (1.0). Large finite per-view conflict losses were observed in the
  0.5 and 1.0 arms and were neither hidden nor used for manual tuning.

## 2026-08-07 — Phase 3 E3–E6 full training complete

- All four locked technical-development conditions completed 30,000 iterations
  sequentially on GPU 0. Every `control/operation.json` has `exit_code: 0` and
  `scientific_verdict: null`; final checkpoints are under the corresponding
  `runs/*/ckpt/final.pt` directories in the canonical task payload.
- E3 (`runs/E3_GS_IMAGE`) completed in 4,820 s, peaked at 10,407 MiB VRAM, and
  ended with 769,883 Gaussians.
- E4 (`runs/E4_GS_ALS_UNWEIGHTED`) completed in 4,707 s, peaked at 7,435 MiB
  VRAM, and ended with 786,404 Gaussians. Its existing-ALS prior used the
  selected depth weight 0.2 and normal weight 0.1 with `w=1`; large finite
  prior-conflict losses were retained without intervention.
- E5 (`runs/E5_GS_ALS_WB`) completed in 4,690 s, peaked at 7,059 MiB VRAM, and
  ended with 761,814 Gaussians. The E4/E5 overlay diff contains only condition
  identity/output paths and `external_als_apply_building_weight: false -> true`;
  seed, initialization, training schedule, random seed, and loss weights are
  identical.
- E6 (`runs/E6_GS_LOD2_PLANES_DIAGNOSTIC`) completed in 4,990 s, peaked at
  11,081 MiB VRAM, and ended with 761,359 Gaussians. It remains diagnostic-only:
  wall/roof weights are 0.3/0.1 with the locked 1 m distance and 30 degree
  normal-angle gates, and no scientific verdict is assigned.
- Historical E1 is the exact current-epoch 2024 ULS Roofer baseline, not the
  existing ALS prior shown in the reference panel. Historical E2 is the exact
  common-base MVS Roofer baseline. This lineage distinction must remain visible
  in the viewer and report.

## 2026-08-07 — direct depth-fusion point-cloud override

- The initial Phase-4 extraction implementation followed the written 5.1 step
  literally: it extracted a TSDF mesh and poisson-disk resampled that mesh at
  75 pt/m2 before Roofer. E3, E4, and E5 completed that path; E6 was in the
  resampling step when the human reviewer clarified the intended lineage.
- The latest controlling instruction is now explicit: rendered training-view
  depth is fused into a TSDF volume, `extract_point_cloud()` is called directly
  on that volume, and this direct depth-fusion point cloud goes immediately to
  the common Roofer classification/read-out. The TSDF mesh remains evaluation
  evidence only and is not allowed to generate Roofer input points.
- The completed mesh-resampled E3/E4/E5 point-cloud directories are retained
  under the task quarantine as rejected lineage and are not Roofer inputs. E6's
  in-progress resampling container was stopped without promoting a receipt.
- The first E3 Roofer attempt used a newly written classification wrapper. The
  human reviewer required reuse of the already certified original-global v3
  script, so that attempt was stopped and quarantined. The active adapter now
  imports and calls `c1_c2_shared_footprint_199_v3/run.py::_common_stages` and
  `_class_counts` directly, retaining its exact SMRF, non-ground footprint
  overlay, no-voxel-downsampling, EPSG:25832 verification, Roofer defaults, ROI,
  image digest, and one-invocation policy. Only the readers.ply source is bound
  to each E3-E6 direct depth-fusion point cloud.

## 2026-08-07 — Phases 4–6 complete

- Direct TSDF-volume point-cloud extraction completed from the 820 training
  views with zero held-out integrations: E3 3,472,605 points, E4 1,197,476,
  E5 1,180,197, and diagnostic E6 2,909,402. Every v2 extraction receipt states
  `TSDF_VOLUME_EXTRACT_POINT_CLOUD_DIRECT` and
  `mesh_used_to_create_roofer_pointcloud: false`.
- Six Roofer outputs exist for E1–E6. E3–E6 classification receipts prove use
  of the certified original-global v3 adapter, EPSG:25832, ground/building
  classes 2/6, no voxel downsampling, Roofer defaults, and one invocation. E1
  remains the historical current-epoch 2024 ULS result and E2 the exact
  common-base MVS result.
- The eight-slot synchronized viewer is under `viewer/`: E1–E6 Roofer, raw
  existing ALS prior, and original existing LoD2. It contains the fixed E3–E6
  themes and per-building `w_b` lookup data.
- Evaluation-scan-only semantic GT contains 117 held-out label PNGs, 117 valid
  masks, and three 300-pixel QA sheets. Its CSF/PCA20 source path is separate
  from all training caches.
- Four condition metrics and `report.md` completed. Change-region ghost volume
  is 225.7236 m3 for E4 and 123.3354 m3 for E5, so the preregistered technical
  relation E4 > E5 is observed. E4/E5 hole areas are 1629.0/2006.5 m2. No
  scientific verdict is assigned. CloudCompare CLI was unavailable in the
  pinned images, so mesh-to-cloud receipts identify the Open3D/SciPy fallback.

## 2026-08-07 — handoff closure validation issue

- A `200-verified` successor receipt was added after all technical artifact
  checks passed, but repository validation rejects the chain because the
  immutable `100-accepted` packet allowed only its handoff-manifest directory
  while the authorized Experiment Host execution subsequently committed changes
  under `scripts/`, `src/`, `tests/`, and `phases/`. Successor receipts cannot
  expand that invariant scope. The failed validator output is not hidden and no
  `300-closed` receipt is issued. Repair requires a separately authorized new
  handoff chain; it must not rewrite the accepted packet or existing commits.
