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
