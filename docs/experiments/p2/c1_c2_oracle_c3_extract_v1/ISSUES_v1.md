# C1/C2 oracle + C3 extraction issue log v1

## CLOSED — insufficient-evidence oblique status text

Recovery v8 successfully produced five roof-only meshes and the exact one-point
insufficient-evidence record for `C3_2_SEM_DEPTH/DEBY_LOD2_4907177`, then stopped
during qualitative composition because the new oblique status panel called the 2D
`Axes.text` signature on a 3D axes. This is a presentation renderer failure, not GS,
mesh-selection, C1/C2, or Roofer failure. Recovery v9 uses `Axes3D.text2D`, regression
tests all four fixed views, and preserves the v8 partial.

## CLOSED — C3 context row and Gaussian primitive representation

Recovery v4 displayed the exact-checkpoint Gaussian proxy as center-point scatter and
did not repeat the current RGB + 2022 LoD2 roofline row in each C3 sheet. Recovery v5
adds the same projection-context row and renders deterministic display subsets as
oriented 2D ellipse polygons from checkpoint quaternion, in-plane scale and opacity.
The exact full Gaussian PLY remains unchanged, and this presentation recovery invokes
neither training nor extraction. Original-resolution v5 review then found that the
long Gaussian titles overlapped adjacent columns; v6 shortens only those labels while
preserving the same primitive display contract and zero-compute counters.
Before v6 execution, the user also requested thicker RGB rooflines and the same
footprint context already present in C1/C2 on every C3 3D row. The combined v7 render
uses a 12 px dark casing with a 6 px yellow roofline and orange dashed GT
`GroundSurface` XY in Gaussian, fused-point and Poisson-mesh views. No v6 artifact
namespace was created.

## OPEN — C3 extracted geometry quality observations

Original-resolution review of all six C3 case sheets found a large detached vertical
surface in `C3_2_SEM_DEPTH/DEBY_LOD2_4906975`, sparse or vertically elongated geometry
for `DEBY_LOD2_4907177` in both conditions, and residual context/clutter around
`DEBY_LOD2_108580336`. The exact Gaussian, fused-point and Poisson-mesh files are
present and hash-valid, so these observations are not renderer or missing-artifact
failures. They remain non-confirmatory technical diagnostics with
`scientific_verdict: null`.

## CLOSED — recovery v10 inherited mesh add-once collision

The first v10 launcher attempt supplied an invalid source-commit string and stopped at
the clean ancestry gate before creating an artifact namespace. The second attempt used
the exact commit and hash-verified the recovery-v9 C1/C2 and C3 payloads, then incorrectly
called `remesh-roof-only` even though recovery-v9 already contained those add-once files.
It stopped on the first existing roof-mesh input PLY before C3 Roofer preparation.
The v10 partial is preserved. Roofer, C3 extraction, GS training, G2 and metric invocation
counts for both stopped attempts are zero. Recovery v11 removes the redundant remesh step,
inherits the completed v9 mesh receipts unchanged, and uses a fresh namespace.

## CLOSED — C3 mesh input included non-roof semantic classes

Recovery v7 Poisson reconstruction consumed every inherited fused point after only
the spatial crop; semantic labels were retained for color but not used as a mesh
filter. This mixed roof, wall, ground and background evidence and produced cluttered
surfaces that did not answer the roof-reconstruction question. Recovery v8 reuses the
exact v7 fused PLY without checkpoint rendering, selects only semantic class `1=roof`
inside the GT GroundSurface XY 1 m buffer, and runs Poisson only when at least 100
selected points exist. Five of six condition/building combinations meet the minimum.
`C3_2_SEM_DEPTH/DEBY_LOD2_4907177` has one selected roof point and therefore shows
`INSUFFICIENT_ROOF_SEMANTIC_EVIDENCE` instead of a fabricated mesh.

## CLOSED — C3 two-dimensional mesh panel axes

Recovery v3 completed both extraction-only C3 conditions: exact full Gaussian PLY,
display proxy, three rendered-depth fused point clouds and three Poisson meshes per
condition. Final presentation then stopped because the TOP/PRINCIPAL_SECTION branch
of the mesh renderer referenced `ax` without first constructing a 2D axes. Recovery
v4 adds the missing axes, regression-tests both two-dimensional views, hash-verifies
and inherits all 16 core C3 files, and performs no GPU extraction or GS training.

## CLOSED — C3 extraction lazy CUDA cache path

Recovery v2 completed all four independent Roofer operations, then exported the full
C3-1 Gaussian PLY and stopped at the first surface render because gsplat attempted to
build its lazy CUDA extension under unwritable `/.cache`. No C3 surface or mesh was
produced, and GS training remained zero. Recovery v3 verifies and inherits the exact
C1/C2 inputs, footprints, terminals and CityJSONSeq outputs without another Roofer
invocation, then mounts a task-local writable Torch/CUDA cache for both C3 conditions.

## CLOSED — zero-class6 pre-Roofer statistic

Recovery v1 reached the expected `DEBY_LOD2_4907177/C2 class-6=0` condition but tried
to compute the minimum and maximum Z of that empty array. It stopped before writing
prepared records and before every Roofer/C3 extraction invocation. The preserved
Recovery-v1 partial is empty. Recovery v2 records both height extrema as null and
continues to the already-frozen `PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE` path.

## CLOSED — local launcher precreated bind-mount root

The first direct Experiment Host invocation stopped before C1/C2 preparation because
`run_host.sh` precreated the `.partial` directory for a Docker bind mount while the
producer rejected any existing output path. The preserved partial is empty. Roofer,
C3 extraction, G2, GS training and metric invocation counts were all zero. Recovery v1
uses a fresh add-once namespace and permits only an existing empty bind-mount root;
any non-empty root still fails closed.

## OPEN — DEBY_LOD2_4907177 reference/ID alignment

Read-only raw-source preflight found only 25 deterministic 0.2 m C1 class-6 voxels and
0 C2 class-6 voxels inside the 2022 LoD2 `GroundSurface` XY. The other two buildings
have more than 134k class-6 voxels per condition. `4907177` is therefore fixed as two
`PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE` records. Roofer is not invoked and no
other building's output is substituted. This is not a C1/C2 or Roofer execution failure.

Resolution requires an independently reviewed 2022↔2024 identity/epoch association;
it is outside this execution's authority.

## CLOSED — focused test runner mismatch

The pinned project image does not install `pytest`, so the first focused-test command
ended before test collection with `No module named pytest`. The new focused test was
converted to the repository-compatible `unittest` form. Five tests then passed in the
same pinned image. No project dependency was installed or changed.
