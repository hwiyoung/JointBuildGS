# FUS-W1 protocol amendment v3b — ALS-fixed camera co-registration

- Amendment ID: `FUS-W1-AMEND-V3B-COREG-20260725`
- Authorized by: 김휘영
- Authorization recorded: 2026-07-25 KST
- Authorization text: `ALS와 카메라를 정합할 수 있는거야? 그래도 lidar를 시드, loss로 사용하려는 의도를 만족할 수 있을까? 맞다면 제시한 정합을 수행하자`
- Applies after: `FUS-W1-ALIGN-RUN-004`
- Pre-amendment state: three core buildings and 71 views were exposed by the
  failed direct-edge Gate A run; micro-registration attempts 0; learning,
  readout, Roofer, and scoring runs 0.

## 1. Scientific treatment and invariants

The treatment is named:

`LiDAR-assisted camera co-registration + LiDAR seed/supervision`

The ALS is the fixed reference. Its source LAZ bytes, EPSG:25832 coordinates,
class 2/6 labels, and SHA-256 values are immutable. The orthometric-to-
ellipsoidal conversion used for comparison and projection is fixed at
`zeta=45.700 m`; scale is fixed at exactly 1. No zeta or scale search is
allowed.

Only the camera/photo-derived world frame may move. The estimated transform is
defined as:

```text
T_A_from_P: photo ellipsoidal UTM -> ALS ellipsoidal UTM
a = pivot + R (p - pivot) + t
```

The original COLMAP model is never overwritten. A derived sparse model and a
transform receipt are written. For a global transform, cameras and sparse
points must receive the same transform. If a later conditional block transform
is adopted, shared sparse points may not be used for learning unless they are
retriangulated; the W1 ALS seed remains the permitted initialization. The
block-pose publication therefore writes zero shared 3D points and changes every
remaining image observation's `POINT3D_ID` to `-1`. Gate A2 may read those
cameras, but learning remains forbidden until a separately committed
ALS-seed-aware staging path supplies a non-empty per-building initialization.

Arm A and arm B must use the exact same corrected-camera and transform hashes.
The seed remains original ALS class 2/6. Depth and normal supervision remain
rasterizations of that same ALS with the frozen cameras. P0-prime remains an
ALS-only score. Therefore co-registration removes a coordinate nuisance and
does not deform the LiDAR prior toward a learned result.

The approved `GroundSurface XY` exception may be used only for target
addressing, crop masks, and spatial separation. LoD2 Z, RoofSurface, roof type,
semantic class, and final reference model remain forbidden as registration
inputs.

## 2. Result-blind calibration split

All 28 core buildings are excluded from transform fitting and selection.
The first three RUN-004 buildings are labelled `exposed_diagnostic_repeat`;
the untouched 25 are the primary independent Gate A holdout.

Registration controls are selected only from the extension cohort using
pre-existing W2 support metadata and footprint centroids, before reading any
new ALS/photo residual:

- 36 `surface` buildings with existing ALS and DIM LoD2 assembly, positive
  point densities, no footprint overlap with core, and at least 20 m footprint
  distance from core;
- deterministic support-first, then centroid-maximin spatial selection;
- deterministic role pattern gives 18 fit, 9 trigger, and 9 independent check;
- the 36 are marked `calibration_exposed=true` and are excluded from later W1
  extension-only interpretation.

The surface-only calibration stratum is intentional: the pre-existing W2
metadata contains no height/outline building with both ALS and DIM assembly,
whereas 43 eligible surface controls remain outside the 20 m core buffer.
Forcing tier balance would either consume unsupported photo geometry or expose
the core neighbourhood. Tier generalization remains tested only by the core
holdout.

## 3. Single composite registration attempt

The unused one-attempt allowance from v3/v3a is replaced by this single
composite procedure. It is not an additional retry.

### 3.1 Global candidate

- Fit data: controls with role `fit` only.
- Initial state: identity.
- Estimator: deterministic multiscale robust point-to-plane SE(3), fixed scale,
  equal building/surface weighting.
- Surfaces: actual ALS class-6 roof points inside the crop and class-2 ground
  points in the surrounding ring, paired to photo-derived dense 3D points.
- Every control must retain both a usable roof group and a usable ground group.
  Normals require at least six neighbours within 1.5 m and surface variation
  at most 0.15; invalid normals are excluded and are never replaced by a
  fabricated vertical normal.
- Scales: locked in config; no post-result tuning.
- Observability: final robust design rank 6 and normalized condition at most
  1000. A parallel-plane-only solution is rejected rather than regularized
  into apparent identifiability.
- Bounds: rotation at most 0.5 degrees, pivot translation at most 1.5 m, and
  maximum displacement over locked controls at most 1.5 m. Values are never
  clipped.

### 3.2 Identity-first selection on trigger controls

The candidate is never selected on fit residual alone. Trigger controls are
opened only after fitting:

1. If identity already meets the locked absolute 3D criteria, identity is
   frozen.
2. Otherwise the global candidate is frozen only if it meets every absolute
   criterion, improves the building-balanced median by at least 0.05 m and
   20%, and worsens no trigger building by more than 0.05 m.
3. Otherwise a conditional block stage is required; it may use only
   result-blind capture blocks declared from OPF capture-time gaps in the
   committed block CSV. Arbitrary post-result block creation is forbidden.

The frozen base for a required block stage is the global candidate only when
that candidate is valid, has positive trigger median improvement, and worsens
no trigger building by more than 0.05 m; otherwise the block base is identity.
This rule is evaluated without the independent check.

The absolute 3D criteria are: building-balanced symmetric point-to-plane median
at most 0.15 m, all-support P90 at most 0.30 m, bidirectional matched support at
least 0.70, and absolute signed bias at most 0.10 m. Unmatched samples are
censored at the locked correspondence radius before P90 calculation.

### 3.3 Conditional capture-block correction

Capture blocks are fixed from original OPF capture timestamps before residual
measurement. A block correction may be adopted only with at least three fit
buildings and 30 observations for that block, trigger median improvement at
least 0.05 m and 20%, no trigger building worsening over 0.05 m, translation
at most 0.5 m, rotation at most 0.15 degrees, maximum displacement at most
0.5 m, and independent-check support for every adopted block.

Block-labelled photo geometry is the committed set of 937 COLMAP geometric
depth maps (`2,843,932,739` bytes; SHA256-sum stream aggregate
`f139071c5b0c3f5129aa3ac1b23fa99ac1a497213f2760a57b0ada44e3448625`).
Pixels are sampled on a fixed stride of 16, interpreted as camera-Z depth in
`[0.1, 200] m`, unprojected through the original COLMAP intrinsics and poses,
converted from canonical to photo ellipsoidal UTM, and assigned only through
the same locked roof/ground XY and fixed-Z windows. A block transform composes
after the global base: `T_block = Delta_block * T_global`.

If block-labelled geometric evidence is required but unavailable or
rank-deficient, the run is BLOCKED. No building-specific ICP and no arbitrary
block inference are allowed.

## 4. Independent check, pose publication, and Gate A

After trigger selection the transform choice and SHA-256 are frozen. The nine
`check` controls are then opened exactly once. Every check building must meet
the absolute 3D criteria above. Failure causes BLOCKED; there is no fallback to
another candidate and no parameter, split, zeta, matcher, or threshold change.

Fit, trigger, block-fit, block-trigger, check, and pose publication are
exact-once stages. Every receipt binds the same Git HEAD, config hash, locked
input hashes, split/block hashes, ALS materialization receipt, and immediate
parent receipt SHA. Existing outputs cannot be overwritten or replayed.

Only a passed independent check permits derived camera-pose publication. The
pose update is locked as:

```text
T_local = S * T_A_from_P * inverse(S)
E_camera_from_A = E_camera_from_P * inverse(T_local)
```

Projection invariance and camera-center transformation are mandatory tests.
The transform is then frozen and Gate A is rerun once on the exact core cohort:
the untouched 25 are the primary independent result and the exposed three are
reported separately. Existing Gate A thresholds are unchanged:

- per-building direct residual median at most 0.30 m;
- every selected view valid;
- systematic offset norm and bootstrap CI upper at most 0.10 m.

No additional XY micro-registration is allowed after this composite attempt.
Learning remains forbidden until all required core Gate A conditions pass.
The committed `--coreg-lock2` mode binds the exact passed pose-publication
manifest and its parent receipt chain, uses distinct `w1_align2_*` outputs, and
sets the permitted post-coreg micro-registration attempt count to zero.

## 5. Publication and failure policy

RUN-004 and all earlier outputs remain immutable. New split, block, residual,
transform, pose, manifest, quantitative tables, and qualitative figures use
new `w1_coreg_*` / `w1_align2_*` paths. Every failure is appended to
`issues.md`. The existing three-repeat catastrophe rule and serial/RAM
constraints remain active.

This amendment changes only the registration procedure after RUN-004. It does
not relax Gate A, authorize learning on a failed gate, modify the ALS, or
change the human-only judgment rule.
