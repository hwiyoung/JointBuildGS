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

## 2026-08-07 — 8876 viewer promotion

- The completed E1–E6 eight-slot viewer package was promoted to host port 8876
  from the canonical external payload `viewer/` directory. Browser-side WebGL
  validation loaded all eight panels, 199 building records, synchronized camera
  control, and null scientific verdict state.
- The former 8876 LiDAR/MVS-only one-shot container was stopped and Docker
  automatically removed that container instance. Its immutable viewer payload
  remains unchanged, so the service is reproducibly recoverable. The temporary
  C3 WEB-v2 service on 8877 was left unchanged.
- Evaluation-only initial semantic outputs remain under `prep/semantic_gt/`:
  117 held-out label PNGs, 117 valid masks, three QA sheets, and `receipt.json`.
  They are generated from the current evaluation scan and are not training
  labels.

## 2026-08-07 — 8876 cache recovery, semantic visualization, and TensorBoard

- A user browser remained at `불러오는 중` because host port 8876 reused the
  previous viewer's unversioned `app.js` URL. Server evidence showed repeated
  index/manifest requests from the browser without a new application-module
  request; local asset transfer was not the bottleneck. The viewer now versions
  both `app.js` and Three.js URLs and reports module/rejection errors in the
  header. The idempotent viewer builder refreshes static application files even
  when its existing manifest checkpoint is valid.
- Canonical semantic `labels/` remain uint8 class IDs 0–4 and `masks/` remain
  uint8 validity 0/255. Their black/white appearance in a generic image viewer
  is therefore expected, not evidence of empty labels. A separate non-canonical
  human-readable `colorized/` derivative now contains 117 RGB PNGs using the
  frozen roof/red, wall/blue, ground/green, other/yellow palette; `receipt.json`
  records the count and palette.
- TensorBoard 2.17.1 is serving the four existing E3–E6 event directories on
  host port 6006. The service is read-only over the run payload and exposes all
  four 30k histories; this is operational monitoring evidence, not a scientific
  verdict.

## 2026-08-07 — synchronized pan, semantic RGB overlays, and qualitative TensorBoard

- The 8876 viewer now synchronizes translation as well as rotation and zoom.
  Right/middle drag or Shift+left drag pans all eight panels; double-click or the
  `시점 초기화` button restores the frozen initial camera. The cache token was
  advanced to `e1e6-20260807c`.
- `prep/semantic_gt/overlays/` now contains 117 original-RGB overlays. Only the
  human-readable derivative uses 65% semantic colour and one-pixel display
  dilation; canonical class-ID labels and valid masks are unchanged. Each image
  embeds the roof/wall/ground/other legend and the receipt records these display
  parameters.
- Existing 5k, 10k, 15k, 20k, 25k and 30k RGB/depth render PNGs were published
  to the existing E3–E6 TensorBoard runs under `qualitative/v0..v3/{rgb,depth}`;
  the four pre-training sanity images were published under `sanity/*`. This
  added 192 render images and four sanity images without retraining or changing
  checkpoint selection.
- Two qualitative publishers briefly overlapped after an orchestration return
  delay. The later publisher was stopped; its four duplicate/partial event files
  were moved recoverably to
  `quarantine/tensorboard_duplicate_publisher_b10d68bcaebf/`. One complete
  publisher event and receipt remain for each condition.

## 2026-08-07 — 8877 removal, point-density interpretation, and dense semantic GT v1

- The temporary `jbgs-c2-c3-rendered-depth-web-v2-8877` service container was
  stopped and removed after its exact bind mount was verified. Host port 8877 is
  free. The immutable source payload under
  `c2_c3_rendered_depth_shared_footprint_199_v1/` was not deleted, so the prior
  result remains recoverable; only the redundant web-service instance was
  removed.
- E2 has 43,848,711 classified MVS points because the certified original-global
  v3 read-out consumes the direct dense MVS cloud with no voxel downsampling.
  By contrast, E3–E6 render 820 training-view depths into the common 0.533333 m
  TSDF and call `extract_point_cloud()` on the fused volume, yielding 3,472,605,
  1,197,476, 1,180,197, and 2,909,402 raw points respectively. This point-count
  gap is principally a read-out density/resolution difference, not evidence by
  itself that MVS geometry is scientifically better. No post-hoc equal-density
  resampling was introduced because the reviewer locked the direct depth-fusion
  point cloud -> certified Roofer lineage.
- No real construction/demolition set was verified for this bounded run
  (`verified_real_construction_or_demolition_count: 0`). The authoritative
  change-region GT is therefore `prep/synthetic_changes.json`: four simulated
  new constructions by prior removal, two simulated demolitions by donor-prior
  insertion, and three prior-height changes. E1 current-epoch ULS versus existing
  ALS is the correct visual/measurement pair for discovering real temporal
  discrepancies, but it does not promote a building to verified real-change GT
  without registration, threshold, and independent evidence checks. The 8876
  raw Existing ALS panel shows the original prior, whereas E4/E5 training used
  the derived synthetic prior; this distinction must be explicit in any future
  change-inspection viewer.
- A separate evaluation-only dense semantic path now exists under
  `prep/semantic_gt_dense/`. It projects the 0.25 m current-evaluation scan's
  PCA20 rule classes with per-pixel z-buffering, expands only within a 0.30 m
  adaptive surfel radius (maximum 6 pixels), and removes a 2-pixel ignore band
  at class boundaries or depth jumps greater than 1 m. It generated 117 labels,
  117 binary valid masks, 117 RGB overlays, and three QA overlays. Full-file
  validation found no invalid class/mask pairs. Mean valid coverage increased
  from the centre-projection support of 0.210523 to 0.365012.
- Human inspection of the three dense QA overlays finds coherent roof, wall,
  and ground surface regions, but also residual fragmentation and rule-based
  errors around vehicles, trees, roof equipment, and complex facades. This is a
  reproducible automatic dense semantic GT v1 and carries
  `scientific_verdict: null`; it is not promoted as manually verified semantic
  truth. Raster labels remain the evaluation contract. Vector polygonization,
  if later required for annotation editing, must preserve the valid/ignore
  boundary and be treated as a derivative rather than silently changing GT.
- The qualitative TensorBoard slots `v0..v3` are four fixed representative
  members of the 117 held-out images (dataset indices 7, 15, 23, and 31), not
  training stages or model versions. Each slot shows the same camera at the 5k,
  10k, 15k, 20k, 25k, and 30k checkpoints. All held-out images were excluded
  from training and TSDF fusion.
- A sanity image is an input-wiring/alignment check, not an output-quality
  score. Acceptable sanity means projected depth support lands on the matching
  image surfaces, normals have plausible orientation, E4 and E5 have identical
  prior-support pixels, E4 is uniformly weighted while E5 changes only those
  pixels by `w_b`, and E6 plane vectors land on the corresponding wall/roof.
  Systematic image offsets, prior pixels on sky, flipped normals, different
  E4/E5 support, or LoD vectors on unrelated surfaces are alignment failures.

## 2026-08-07 — depth-fusion terminology and change-region viewer overlay

- The E3–E6 Roofer point clouds are not mesh-resampled clouds. Each condition's
  rendered training-view RGB-D is integrated into Open3D's
  `ScalableTSDFVolume`, and Roofer receives the direct return of that volume's
  `extract_point_cloud()`. In this implementation TSDF is the selected depth
  fusion algorithm. This differs from directly back-projecting every accepted
  depth pixel and concatenating/filtering those samples. The 0.533333 m TSDF
  voxel strongly regularizes and thins the surface evidence, so it can improve
  coherence/noise rejection while reducing point density, thin structure, and
  coverage. Any direct-backprojection alternative is a new controlled read-out
  arm and must not be silently substituted into the completed E3–E6 receipts.
- The metric change region is the union of the nine shared standard building
  footprints whose stable IDs occur in `prep/synthetic_changes.json`; it is not
  a new thresholded delta-DSM component. Within that footprint union, evaluation
  rasterizes method and current-evaluation DSMs at 0.5 m. Positive method-minus-
  evaluation height contributes ghost volume where both are finite; an
  evaluation-finite/method-missing cell contributes 0.25 m2 of hole area.
- The live 8876 viewer manifest now carries the same nine exact footprint rings
  and their synthetic operation metadata. Every panel renders vertical wireframe
  regions: red for simulated new construction, cyan for simulated demolition,
  and yellow for prior-height change. The header provides a synchronized
  `변화영역 ON/OFF` control, legend, and click details. Headless Chrome software-
  WebGL validation rendered all eight panels and the nine overlays; manifest
  counts are 8 panels, 199 buildings, and 9 change regions. The cache token is
  `e1e6-20260807d`.
- Dense semantic v1 already performs conservative local growth: each visible
  z-buffered evaluation-scan point owns nearby pixels only within the projected
  radius of a 0.30 m surfel, capped at 6 pixels; competing semantic classes and
  depth jumps create a 2-pixel invalid boundary. More aggressive RGB-guided
  superpixel, CRF, or promptable-mask growth is feasible, but it changes the
  product from geometry-only rendered evaluation labels to image-assisted
  pseudo-labels. For a defensible final dense GT, retain v1 unchanged and create
  any edge-aware v2 separately, require seed-consensus and geometry gates, and
  manually accept/correct its polygons before promotion.

## 2026-08-07 — real temporal candidates, RGB/SAM pseudo-GT v2, and Roofer evidence review

- The nine regions previously displayed as the change-evaluation contract are
  synthetic interventions from `prep/synthetic_changes.json`; they are not
  observed temporal changes. They remain available in the 8876 viewer under the
  separate `합성 평가` toggle and are OFF by default. No historical metric or
  synthetic receipt was relabelled.
- A separate real-temporal-candidate path now compares the current 2024 E1 ULS
  class-6 DSM with the 2022-era existing ALS class-6 DSM at 0.5 m resolution.
  Existing ALS receives the frozen +45.7 m transform; an additional +0.122009 m
  median ground residual is measured from 225,068 overlapping class-2 cells
  outside the standard footprints. The robust ground scale is sigma0=0.050403 m,
  and the conservative operational height threshold is max(1 m, 3 sigma0)=1 m.
  Missing building support is counted only when the other epoch observes ground,
  so absent coverage alone is not treated as change.
- This produced 14 automatic candidates within the 199-building population. Of
  these, 11 pass the stronger signal-size rule and are labelled
  `STRONG_SIGNAL`; that label is deliberately not `HIGH` or `VERIFIED`.
  `verified_real_change_count` remains zero until independent or human temporal
  confirmation. The GeoJSON geometry is the union of detected 0.5 m change
  cells clipped by each footprint, rather than the full footprint. It is under
  `prep/real_change_candidates/` with a v4 receipt and overview.
- The live 8876 viewer now defaults to the real-candidate partial polygons and
  keeps synthetic regions OFF. It also displays deterministic class-2/class-6
  adapters of the exact E1-E6 classified point clouds consumed by Roofer. The
  exact sources are not modified. Exact/display point counts are E1
  177,968,343/598,939, E2 43,848,711/596,329, E3 2,331,652/439,308, E4
  1,168,590/507,405, E5 1,137,866/494,682, and E6
  1,879,921/532,125. A software-WebGL browser capture loaded all eight panels,
  point adapters, and 14 partial candidate overlays.
- `prep/semantic_gt_rgb_sam_v2/` is a separate evaluation-only RGB-assisted
  pseudo-GT derivative. It freezes every geometry-dense-v1 seed pixel, expands
  only high-purity RGB SLIC regions, then uses the pre-existing pinned SAM ViT-B
  checkout/checkpoint with geometry-seed support, purity, recall, and predicted-
  IoU acceptance gates. Across all 117 held-out views, mean valid coverage rises
  from 0.365012 to 0.535771; SLIC adds 22,653,640 pixels and 1,088 accepted SAM
  masks add 6,693,460 pixels. Validation found zero changed seed pixels and zero
  label/mask inconsistencies. The output still requires human review and is not
  promoted as verified GT; trees, vehicles, roof equipment, and complex facades
  remain known error modes.
- Read-out code inspection confirms two distinct depth-fusion choices. The
  completed E3-E6 arm integrates alpha-filtered **expected depth** into a
  0.533333 m Open3D TSDF and passes `extract_point_cloud()` directly to Roofer.
  The previously used repository extraction path instead takes 2DGS **median
  surface depth**, back-projects each view, voxel-fuses by distinct-view votes,
  and applies statistical outlier removal. The newer certified C3 extractor uses
  the same median-depth consensus principle at 0.15 m and carries averaged RGB,
  normals, and semantic votes. The visual point evidence confirms that read-out
  density and support differ materially, but it does not by itself establish
  which geometry is more accurate.
- Decision for this review: do not silently replace the completed E3-E6
  receipts. The next bounded technical action, if authorized, is one E3
  extraction-only A/B using the existing median-depth consensus code with the
  same checkpoint and training views, followed by the exact same certified
  classification/Roofer path. Compare footprint coverage, class-6 evidence
  count, held-out depth/mesh distance, hole area, ghost volume, Roofer building
  completion, and runtime. If it is operationally preferable, re-extract E3-E6
  without retraining while preserving the current TSDF arm as the baseline.

## 2026-08-07 — reviewer visual correction and E2-E6 surface-mesh comparison

- Human visual review did not find an unambiguous building-form change in most
  of the 14 ALS/ULS automatic candidates; only a lower-edge case was considered
  potentially worth further inspection. The automatic output therefore remains
  cross-epoch **sensor-difference evidence**, not real-change GT. Its v5 receipt
  says this explicitly, keeps `verified_real_change_count: 0`, and adds the
  visual-review limitation. The viewer label is now `시점차 후보`, default OFF.
  No candidate will count as a real change without independent imagery or human
  confirmation.
- The exact common E2 MVS recovery contained dense depth maps, 43,926,567 MVS
  points in `dim_dense.mvs`, and no completed MVS surface mesh: the historical
  recovery intentionally stopped before mesh after its byte-comparison gate.
  For this authorized viewer-only comparison, pinned OpenMVS
  `ReconstructMesh` read the exact project and 937 calibrated images, generated
  a 15,764,959-face raw graph-cut surface, then applied the recorded OpenMVS
  cleanup and 0.25 decimation to 1,956,560 vertices / 3,911,218 faces. This is a
  new display/evidence derivative and does not modify E2 Roofer or its input.
- E3-E6 already contained their exact evaluation TSDF meshes: 6,254,203,
  2,158,627, 2,131,836, and 5,304,376 faces. E2-E6 were each converted to an
  approximately 180,000-face Open3D quadric display proxy, recorded with exact
  source and asset hashes in `viewer/surface_meshes.json`. E1 remains native ULS
  point evidence because no frozen E1 surface mesh exists; no arbitrary Poisson
  mesh was invented for it.
- The live 8876 viewer now has independent `Roofer`, `Roofer점군`, and
  `표면mesh` toggles. Surface meshes load lazily so the default view does not pay
  the extra transfer cost. `?mode=surface` opens a clean surface-only view with
  Roofer, point clouds, and sensor-difference candidates OFF. Software-WebGL
  validation loaded E2 OpenMVS and E3-E6 TSDF proxies under the synchronized
  camera.
- Visual observation, not a scientific verdict: E2's OpenMVS surface is broad
  and coherent enough to explain why shared-footprint Roofer completes nearly
  all buildings. E3 has visibly more detached/floating surface and boundary
  noise; E4/E5 are substantially cleaner and similar to one another; E6 retains
  more edge/outside fragments. This makes aggregate completed-building count a
  likely ceiling metric for this scene. Any method claim should also examine
  roof-plane/height distance, holes, ghost geometry, topology, and predeclared
  difficult/change strata rather than forcing an improvement over a strong MVS
  baseline.
- RGB/SAM v2 cannot defensibly fill every remaining invalid pixel: many gaps are
  caused by no evaluation-scan visibility, occlusion, or an unsupported region,
  not only a missing image segment. The recommended denser evaluation derivative
  is a v3 pilot that triangulates projected evaluation-scan samples per held-out
  view and rasterizes only same-class triangles passing 3D-edge and depth-jump
  gates, then clips their edges by SAM/RGB regions. Remaining unsupported regions
  stay invalid unless manually polygon-labelled. Simple dilation or assigning
  every SAM mask would increase coverage but would not constitute reliable GT.

## 2026-08-07 — E4/E5 surface-coverage diagnosis and dense-evaluation-scan correction

- The initial surface-only browser used an approximately 180k-face wireframe
  proxy. Wireframe made every decimation edge visible and exaggerated the visual
  impression of fragmentation. The same proxies are now rendered as solid,
  condition-coloured, flat-shaded surfaces. This display correction does not
  change the source meshes or their measured missing support.
- E4/E5 do have a real extraction-coverage loss relative to E3. All conditions
  integrate the same 820 training cameras using alpha >= 0.5 and the same
  0.533333 m TSDF. E3 integrates 1,011,125,108 valid rendered pixels, whereas E4
  and E5 integrate 487,894,712 and 480,738,858. Held-out valid ratios are
  0.912708, 0.482559, and 0.477242. Their extracted clouds contain 3,472,605,
  1,197,476, and 1,180,197 points and their meshes contain 6,254,203, 2,158,627,
  and 2,131,836 faces.
- This is not explained by fewer Gaussians: E3/E4/E5 have 769,883 / 786,404 /
  761,814 primitives. The final opacity distributions differ. Mean opacity is
  0.350082 / 0.256960 / 0.256174, median opacity is 0.115695 / 0.044989 /
  0.044833, and the fraction of primitives with opacity >= 0.5 is 0.332693 /
  0.227210 / 0.226415. Thus the common hard alpha extraction gate removes much
  more E4/E5 rendered support. This identifies the immediate read-out mechanism;
  it does not yet prove whether outdated-ALS supervision, optimization, or the
  expected-depth renderer caused the lower opacity.
- Roofer does **not** receive points sampled from `tsdf_mesh.ply`. The extraction
  calls `volume.extract_triangle_mesh()` and `volume.extract_point_cloud()`
  independently on the same Open3D TSDF volume. `prepare_roofer.py` then reads
  only `pointcloud/depth_fusion.ply`. The mesh is retained for evaluation and
  display. Roofer can look much cleaner because the certified adapter classifies
  the cloud, Roofer uses the shared footprint, ignores irrelevant evidence, fits
  planes, and closes/regularizes incomplete support into a LoD model.
- The safe next extraction diagnostic is common across all GS conditions: sweep
  shared alpha gates and compare expected-depth TSDF against the pre-existing
  median-surface-depth, distinct-view-consensus fusion. Do not lower only E4/E5
  or silently overwrite completed receipts. This extraction-only check requires
  no retraining.
- The semantic path did start from the current evaluation ULS, but the CSF
  pipeline then applied a 0.25 m voxel-centre filter for tractable PCA20. The raw
  evaluation scan has 177,981,904 points; the classified semantic cloud has only
  7,084,652. The reviewer is therefore correct that a denser evaluation cloud is
  the first lever before additional SAM growth.
- Recommended semantic v3: retain the 0.25 m PCA20 cloud as stable semantic
  anchors, transfer its labels with distance/geometry gates to a 0.10 m or raw
  evaluation-ULS derivative, and z-buffer that denser cloud into held-out views.
  Use class-consistent triangle/surfel filling for residual within-surface gaps
  and SAM only to clip RGB boundaries. Do not use MVS dense points for evaluation
  GT because that would mix the image-derived training source into the separate
  evaluation path.

## 2026-08-07 — raw-evaluation-ULS semantic image pilot

- A three-view evaluation-only pilot now isolates the input-density change as
  closely as practical. It retains the frozen 0.25 m CSF/PCA20 labels as
  semantic anchors, streams the original 177,981,904-point current-evaluation
  ULS once, transfers the nearest anchor label within 0.45 m, and z-buffers the
  denser points into held-out views 0, 58, and 116. The existing 0.30 m surfel,
  six-pixel cap, class/depth boundary ignore, SLIC, and SAM gates are unchanged.
  It does not recompute PCA20 on all raw points and does not use MVS or training
  labels. Outputs are separate under `prep/semantic_gt_dense_scan_pilot_v1/`
  and `prep/semantic_gt_dense_scan_rgb_sam_pilot_v1/`.
- Geometry-only valid fractions change from 0.4651/0.3219/0.4341 with the
  0.25 m input to 0.5513/0.3385/0.4806 with raw ULS projection: gains of
  8.62, 1.65, and 4.64 percentage points. After the identical RGB/SAM stage,
  valid fractions change from 0.6685/0.4715/0.6055 to
  0.7078/0.4856/0.6421: gains of 3.93, 1.41, and 3.67 points.
- Four-panel comparisons are under
  `prep/semantic_gt_dense_scan_pilot_comparisons_v1/`. Visual inspection shows
  that denser evaluation support fills genuine within-surface gaps, especially
  on broad roofs and ground. It also makes existing anchor-label noise denser;
  roof equipment, vegetation, facade details, and some roof patches remain
  `other` or mixed. Therefore this is a useful input-density pilot, not verified
  polygon GT. A final promotion still needs region/polygon cleanup and human QA.
- TSDF interpretation is also fixed: mesh extraction is not identified as the
  primary source of the E4/E5 height/support loss. `extract_triangle_mesh()` and
  `extract_point_cloud()` independently read the same TSDF zero surface. The
  hard rendered-alpha selection and coarse TSDF integration happen before both.
  Roofer can reconstruct a complete LoD building from partial in-footprint roof
  evidence by fitting and regularizing planes, so its output can look much more
  complete than either raw TSDF derivative without proving the input cloud is
  geometrically complete.

## 2026-08-07 — reviewer-directed MVS semantic pilot and GS quality diagnosis

- The reviewer explicitly selected the current-image MVS dense point cloud as
  the semantic source. This supersedes the earlier recommendation against MVS
  for this three-view pilot only. The new path contains no LiDAR input: it reads
  `p0-audit/data/work/mvs/dim/dim_v1.laz` (43,942,554 points), runs CSF and a
  0.10 m voxel anchor for PCA20/height rule labels (25,733,235 points), transfers
  those labels back to all cropped raw MVS points within 0.20 m, z-buffers them
  into held-out slots 0/58/116, and applies the existing conservative SLIC/SAM
  image-boundary growth. Outputs are under
  `prep/semantic_mvs_anchor_pilot_v1/`, `prep/semantic_mvs_raw_pilot_v1/`, and
  `prep/semantic_mvs_raw_rgb_sam_pilot_v1/`.
- This derivative is named **current-image-derived MVS pseudo-GT**, not an
  independent evaluation GT. It inherits MVS reconstruction errors and shares
  image lineage with the methods being assessed. It is suitable for visualizing
  the requested image-only labeling workflow or for provisional labels, but not
  for an independent claim that an image-derived method matches sensor GT.
- Raw-MVS geometry-only valid fractions are 0.3947/0.3897/0.2998. Conservative
  RGB/SAM growth raises them to 0.6127/0.5730/0.6506. Visual QA shows that more
  points fill support, but density alone does not fix rule-class accuracy: sloped
  roof patches are split between roof/other, facade detail is mixed wall/other,
  and vegetation remains noisy. Polygon-quality labels require multi-scale
  plane/region aggregation or manual polygon QA after this seed stage.
- A 30k held-out RGB contact sheet is stored at
  `report_assets/gs_quality_review_v1/heldout_rgb_30k_contact_sheet.png` with
  the input image and E3-E6 in identical view slots. E3 and E6 retain major roof
  appearance but are blurred and geometrically softened. E4/E5 contain extensive
  black unsupported regions and needle-like high-frequency artifacts already in
  the renderer, before TSDF meshing.
- Current technical diagnosis: completion of 30k optimization is not equivalent
  to successful geometric reconstruction. E4/E5 degrade from 5k to 30k in
  held-out PSNR (12.5191 to 11.2461; 12.1489 to 11.0810), MVS-depth MAE
  (4.3300 to 8.5483 m; 5.4648 to 9.9557 m), and normal cosine
  (0.5437 to 0.4946; 0.5327 to 0.4829). Their held-out scan-depth support is only
  0.4826/0.4772 and hole area is 1,629.0/2,006.5 m2. This demonstrates an
  optimization/prior-interaction failure in addition to alpha/TSDF read-out loss.
  E3 is a partial appearance result (final held-out PSNR 15.3112) but not precise
  geometry (scan-depth RMSE 27.9414 m). E6 is optimization-stable against the MVS
  depth cache (2.7000 m MAE at 30k) but still has scan-depth RMSE 29.9976 m and
  fragmented geometry; its logged LoD-plane support is very small. No condition
  currently demonstrates both convincing held-out rendering and accurate,
  complete LoD-ready geometry. These are technical observations;
  `scientific_verdict` remains null for human review.

## 2026-08-07 — E3 local distortion and fusion-control diagnostic

- Building 4906982 was retrained on the fixed 47-train/8-validation local crop
  with the cropped SfM sparse seed, no MVS depth/normal loss, no external prior,
  opacity reset effectively disabled (`reset_every=100000`), and all settings
  held fixed except depth-distortion weight. The `w_distort=100` v7 pilot was a
  loss-scale failure: at step 3000 its weighted distortion contribution was
  about 10.33 and validation PSNR peaked at 15.5966 dB before falling. It is
  retained as negative technical evidence. The `w_distort=0.1` v8 pilot selected
  step 7000 by the locked eight-view mean validation PSNR rule (17.3841 dB;
  checkpoint SHA-256 `cde1655bc3f65b9990154b8992c60b7163cebfc514f333488f28f52177e4400a`).
- The v8 value is slightly below the otherwise matched distortion-off v6 step
  7000 validation PSNR (17.4806 dB). It reduces the absolute maximum Gaussian Z
  but not the robust upper tail or high-Z count: v8 has 261 Gaussians above
  world Z 650 m (259 opaque), versus v6 182 (159 opaque). Distortion alone has
  therefore not removed the learned high geometry in this bounded run.
- The exact same selected v8 checkpoint was read out in two arms. Baseline TSDF
  uses the established expected-depth and alpha>=0.5 path. The filtered arm adds
  current-image-SfM per-view 1--99 percent depth bounds with a 10 m margin and
  requires support from at least three distinct views before the same TSDF
  integration. Baseline integrates 29,351,614 pixels and emits 2,295,647 points;
  filtered integrates 21,176,623 pixels and emits 1,442,001 points. Points above
  Z 650 m fall from 311,343 to 177,838 (42.88%), while all points fall 37.19%.
  The remaining high structures visible in the viewer show that read-out
  filtering is only a partial suppression, not a repair of learned geometry.
- Roofer used identical footprints and parameters for both read-outs. `--jobs 1`
  had no scientific-control justification, so the interrupted single-worker
  diagnostic was restarted with `ROOFER_JOBS=12`; Roofer allocated 11
  reconstruction workers. Baseline processed 179 buildings in about 4m09s and
  filtered in about 2m29s. For 4906982, baseline/filtered point density is
  30.7726/21.4588 pt/m2, no-data fraction 0.02112/0.03736, LoD2.2 RMSE
  3.0757/3.2534 m, roof-plane count 249/223, and roof median/max Z
  583.47/634.67 versus 582.91/583.66 m. These are observations only;
  `scientific_verdict` remains null.
- Viewer 8876 now offers both `DIST0P1_BASELINE_7K` and
  `DIST0P1_CONSENSUS3_7K` without replacing the earlier E3 variants. The checked
  filtered screenshot is stored under the v8 task at
  `control/8876_dist0p1_consensus3.png`; all newly referenced OBJ and surface
  mesh assets returned HTTP 200.
